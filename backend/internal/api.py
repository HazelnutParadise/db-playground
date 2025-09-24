import pandas as pd
import io
import internal.execute as execute
import internal.csv_to_sql as c2q
from fastapi import APIRouter, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse
from typing import Any
from pydantic import BaseModel, field_validator, ValidationInfo

from internal.consts import ALLOW_DB_TYPES_AND_VERSIONS
from internal.ask_ai_for_help import ask_ai_for_help as ask_ai_for_help_func

api_router = APIRouter(
    prefix="/api", tags=["api"]
)


@api_router.get("/databases")
async def get_db_list() -> JSONResponse:
    db_list: dict[str, list[str]] = ALLOW_DB_TYPES_AND_VERSIONS
    return JSONResponse(content={"databases": db_list})


class ExecuteRequest(BaseModel):
    db_type: str
    db_version: str
    schema_sql: str | None = None
    query_sql: str | None = None

    @field_validator('db_type')
    def validate_db_type(cls, v: str) -> str:
        if v not in ALLOW_DB_TYPES_AND_VERSIONS:
            raise ValueError(
                f"db_type must be one of {ALLOW_DB_TYPES_AND_VERSIONS.keys()}")
        return v

    @field_validator('db_version')
    def validate_db_version(cls, v: str, info: ValidationInfo) -> str:
        db_type: str = info.data['db_type']
        if v not in ALLOW_DB_TYPES_AND_VERSIONS[db_type]:
            raise ValueError(
                f"db_version must be one of {ALLOW_DB_TYPES_AND_VERSIONS[db_type]} for db_type '{db_type}'")
        return v


@api_router.post('/execute')
async def execute_sql(request: ExecuteRequest) -> JSONResponse:
    db_type: str = request.db_type
    version: str = request.db_version
    schema_sqls_str: str | None = request.schema_sql
    queries_str: str | None = request.query_sql

    if not schema_sqls_str and not queries_str:
        return JSONResponse(status_code=400, content={
            "status": "error",
            "result": "No SQL to execute"
        })
    assert schema_sqls_str is not None
    assert queries_str is not None
    schema_sqls: list[str] = await execute.parse_queries(schema_sqls_str)
    queries: list[str] = await execute.parse_queries(queries_str)
    try:
        response: dict = await execute.execute_sql_statements(db_type, version, schema_sqls, queries)
        if not response:
            return JSONResponse(content={
                "status": "success",
                "result": "No query executed."
            })
        return JSONResponse(content={
            "status": "success",
            "result": response
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "result": str(e)
        })


@api_router.post("/csv-to-sql")
async def csv_to_sql(file: UploadFile = File(...), table_name: str = Form(...)) -> JSONResponse:
    if file.content_type == 'text/csv':
        try:
            contents: bytes = await file.read()
            df: pd.DataFrame = pd.read_csv(io.StringIO(
                contents.decode('utf-8')), skip_blank_lines=True)
            header_row: int = c2q.find_header_row(df)
            df = pd.read_csv(io.StringIO(
                contents.decode('utf-8')), header=header_row)
            df = c2q.remove_empty_or_nan_rows_or_columns(df)
            sql: str = c2q.create_sql_from_df(df, table_name)
            return JSONResponse(content={"sql": sql})
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
    else:
        return JSONResponse(status_code=400, content={"error": "Invalid file type"})


class LLMHelpRequest(BaseModel):
    db_type: str
    db_version: str
    schema_sql: str | None = None
    query_sql: str | None = None
    error_message: str

    @field_validator('db_type')
    def validate_db_type(cls, v: str) -> str:
        if v not in ALLOW_DB_TYPES_AND_VERSIONS:
            raise ValueError(
                f"db_type must be one of {ALLOW_DB_TYPES_AND_VERSIONS.keys()}")
        return v

    @field_validator('db_version')
    def validate_db_version(cls, v: str, info: ValidationInfo) -> str:
        db_type: str = info.data['db_type']
        if v not in ALLOW_DB_TYPES_AND_VERSIONS[db_type]:
            raise ValueError(
                f"db_version must be one of {ALLOW_DB_TYPES_AND_VERSIONS[db_type]} for db_type '{db_type}'")
        return v


@api_router.post("/call-llm-for-help")
async def call_llm_for_help(request: LLMHelpRequest) -> JSONResponse:
    result: str | None = ask_ai_for_help_func(data={
        'db_type': request.db_type,
        'db_version': request.db_version,
        'schema_sqls': request.schema_sql,
        'queries': request.query_sql,
        'error_message': request.error_message
    })
    return JSONResponse(content={
        "result": result
    }) if result else JSONResponse(
        status_code=500,
        content={
            "error": "No response from AI."
        })
