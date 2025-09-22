from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse
import pandas as pd
import io
import internal.execute as execute
import csv_to_sql as c2q
from typing import Any

from internal.ask_ai_for_help import ask_ai_for_help as ask_ai_for_help_func


def set_api(app: FastAPI) -> None:
    @app.post('/execute')
    async def execute_sql(request: Request) -> JSONResponse:
        data: dict[str, Any] = await request.json()
        db_type: str | None = data.get('dbType')
        version: str | None = data.get('version')
        schema_sqls_str: str | None = data.get('schemaSql')
        queries_str: str | None = data.get('querySql')
        if not db_type or not version:
            return JSONResponse(status_code=400, content={
                "status": "error",
                "result": "Missing dbType or version"
            })
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
            response: str = await execute.execute_sql_statements(db_type, version, schema_sqls, queries)
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
            return JSONResponse(content={
                "status": "error",
                "result": str(e)
            })

    @app.post("/csv-to-sql")
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

    @app.post("/call-llm-for-help")
    async def call_llm_for_help(request: Request) -> JSONResponse:
        data: dict[str, Any] = await request.json()
        result: str | None = ask_ai_for_help_func(data={
            'db_type': data.get('dbType'),
            'db_version': data.get('dbVersion'),
            'schema_sqls': data.get('schemaSql'),
            'queries': data.get('querySql'),
            'error_message': data.get('errorMessage')
        })
        return JSONResponse(content={
            "status": "success",
            "result": result
        }) if result else JSONResponse(content={
            "status": "error",
            "result": "No response from AI."
        })
