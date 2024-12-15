from fastapi import FastAPI, HTTPException, Request
import databases
import sqlparse
import uuid
import asyncpg

app = FastAPI()

# 構建資料庫連接字串的函數
async def build_database_url(db_type: str, version: str, db_name: str) -> str:
    version_key = version.replace('.', '')  # 移除版本中的點
    if db_type == "mysql":
        return f"mysql+aiomysql://root:secret@mysql{version_key}/{db_name}"
    elif db_type == "postgres":
        return f"postgresql://postgres:secret@postgres{version_key}/{db_name}"
    else:
        raise ValueError("Unsupported database type")

# 創建臨時資料庫
async def create_temporary_database(db_type: str, version: str) -> str:
    db_name = f"temp_{uuid.uuid4().hex}"
    admin_db_url = await build_database_url(db_type, version, "master" if db_type == "mssql" else "mysql" if db_type == "mysql" else "postgres")

    if db_type == "postgres":
        conn = await asyncpg.connect(admin_db_url)
        await conn.execute(f'CREATE DATABASE "{db_name}"')
        await conn.close()
    else:
        admin_db = databases.Database(admin_db_url)
        await admin_db.connect()
        await admin_db.execute(f"CREATE DATABASE {db_name}")
        await admin_db.disconnect()

    return db_name

# 解析多個 SQL 查詢的函數
async def parse_queries(full_query: str) -> list:
    parsed = sqlparse.split(full_query)
    return [query.strip() for query in parsed if query.strip()]

async def drop_database(db_type, version, db_name):
    if db_type == "postgres":
        try:
            # 連接到 postgres 管理資料庫
            admin_db_url = await build_database_url(db_type, version, "postgres")
            conn = await asyncpg.connect(admin_db_url)
            
            # 先終止所有連到目標資料庫的連線
            await conn.execute(f'''
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = $1
                AND pid <> pg_backend_pid()
            ''', db_name)
            
            # 再刪除資料庫
            await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
            
        except Exception as e:
            print(f"Error dropping database: {str(e)}")
            
        finally:
            await conn.close()

@app.post('/execute')
async def execute_sql(request: Request):
    data = await request.json()
    db_type = data.get('dbType')
    version = data.get('version')
    schema_sqls = await parse_queries(data.get('schemaSql'))
    queries = await parse_queries(data.get('querySql'))

    try:
        db_name = await create_temporary_database(db_type, version)
        database_url = await build_database_url(db_type, version, db_name)
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
                    query_result = await database.fetch_all(query)

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
            return "No query executed."

        return response
    except Exception as e:
        return "error:" + str(e)
    finally:
        await drop_database(db_type, version, db_name)
        await database.disconnect()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)