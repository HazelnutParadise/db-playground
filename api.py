from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse
import databases
import pandas as pd
import io
import execute
import csv_to_sql as c2q
from typing import Any

from ask_ai_for_help import ask_ai_for_help as ask_ai_for_help_func

def set_api(app: FastAPI) -> None:
    @app.post('/execute')
    async def execute_sql(request: Request) -> str:
        data = await request.json()
        db_type = data.get('dbType')
        version = data.get('version')
        schema_sqls = await execute.parse_queries(data.get('schemaSql'))
        queries = await execute.parse_queries(data.get('querySql'))

        try:
            db_name = await execute.create_temporary_database(db_type, version)
            database_url = await execute.build_database_url(db_type, version, db_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    
        database = databases.Database(database_url)
        await database.connect()

        response = ""
        try:
            if schema_sqls:
                for schema_sql in schema_sqls:
                    await database.execute(schema_sql)
                response += f'<h5>Schema executed successfully!</h5><br>'

            if queries:
                query_num = 0
                for query in queries:
                    query_num += 1
                    if query.strip():
                        query_result: Any = await database.fetch_all(query)

                        num_of_rows = len(query_result) if query_result else 0
                        if query_result:
                            columns = list(query_result[0].keys())
                            num_of_columns = len(columns)
                        else:
                            columns = []
                            num_of_columns = 0

                        response += f"<h5>Query #{query_num} [({num_of_rows} rows) * ({num_of_columns} columns)]</h5>"
                        html_content = ""
                        if query_result:
                            # 開始HTML表格
                            html_content = "<table><tr>" + \
                                "".join(f"<th>{col}</th>" for col in columns) + "</tr>"
                            for record in query_result:
                                record = dict(record)
                                record_values = list(record.values())
                                row = "".join(f"<td>{(record_v if record_v is not None else 'null')}</td>" for record_v in record_values)
                                html_content += f"<tr>{row}</tr>"
                            html_content += "</table>"
                        else:
                            html_content = "<blockquote><strong>No results.</strong></blockquote>"
                        response += html_content + "<br>"

            if not response:
                return JSONResponse(content={
                    "status": "success",
                    "result":"No query executed."
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
        finally:
            await execute.drop_database(db_type, version, db_name)
            await database.disconnect()

    @app.post("/csv-to-sql")
    async def csv_to_sql(file: UploadFile = File(...), table_name: str = Form(...)) -> JSONResponse:
        if file.content_type == 'text/csv':
            try:
                contents = await file.read()
                df = pd.read_csv(io.StringIO(contents.decode('utf-8')), skip_blank_lines=True)
                header_row = c2q.find_header_row(df)
                df = pd.read_csv(io.StringIO(contents.decode('utf-8')), header=header_row)
                df = c2q.remove_empty_or_nan_rows_or_columns(df)
                sql = c2q.create_sql_from_df(df, table_name)
                return JSONResponse(content={"sql": sql})
            except Exception as e:
                return JSONResponse(status_code=400, content={"error": str(e)})
        else:
            return JSONResponse(status_code=400, content={"error": "Invalid file type"})
        
    @app.post("/call-llm-for-help")
    async def call_llm_for_help(request: Request) -> JSONResponse:
        data = await request.json()
        result = ask_ai_for_help_func(data={
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
