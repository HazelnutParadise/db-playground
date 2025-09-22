import uuid
import asyncpg
import sqlparse
import databases
from fastapi import HTTPException
from typing import Any


async def _create_temporary_database(db_type: str, version: str) -> tuple[str, asyncpg.Connection | databases.Database | None]:
    db_name: str = f"temp_{uuid.uuid4().hex}"
    admin_db_url: str = await _build_database_url(db_type, version, "master" if db_type == "mssql" else "mysql" if db_type == "mysql" else "postgres")

    conn: asyncpg.Connection | databases.Database | None = None
    if db_type == "postgres":
        conn = await asyncpg.connect(admin_db_url)
        assert conn is not None
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    else:
        conn = databases.Database(admin_db_url)
        await conn.connect()
        await conn.execute(f"CREATE DATABASE {db_name}")

    return db_name, conn


async def _build_database_url(db_type: str, version: str, db_name: str) -> str:
    """根據資料庫類型、版本和資料庫名稱構建資料庫連接字串"""
    version_key: str = version.replace('.', '')  # 移除版本中的點
    if db_type == "mysql":
        return f"mysql+aiomysql://root:secret@mysql{version_key}/{db_name}"
    elif db_type == "postgres":
        return f"postgresql://postgres:secret@postgres{version_key}/{db_name}"
    else:
        raise ValueError("Unsupported database type")


async def parse_queries(full_query: str) -> list[str]:
    """解析多個 SQL 查詢語句，返回查詢列表"""
    parsed: list[str] = sqlparse.split(full_query)
    return [query.strip() for query in parsed if query.strip()]


async def drop_database(db_type: str, version: str, db_name: str) -> None:
    admin_db_url: str = await _build_database_url(db_type, version, "master" if db_type == "mssql" else "mysql" if db_type == "mysql" else "postgres")

    if db_type == "postgres":
        conn: asyncpg.Connection = await asyncpg.connect(admin_db_url)
        try:
            # 終止現有連線
            await conn.execute(f'''
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = $1
                AND pid <> pg_backend_pid()
            ''', db_name)
            # 安全刪除資料庫
            await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            await conn.close()
    else:
        admin_db = databases.Database(admin_db_url)
        await admin_db.connect()
        await admin_db.execute(f"DROP DATABASE IF EXISTS {db_name}")
        await admin_db.disconnect()


async def execute_sql_statements(db_type: str, version: str, schema_sqls: list[str], queries: list[str]) -> str:
    db_name: str | None = None
    conn: asyncpg.Connection | databases.Database | None = None
    try:
        db_name, conn = await _create_temporary_database(db_type, version)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if conn is None:
        raise HTTPException(
            status_code=500, detail="Failed to create temporary database")

    response: str = ""
    try:
        if schema_sqls:
            for schema_sql in schema_sqls:
                await conn.execute(schema_sql)
            response += f'<h5>Schema executed successfully!</h5><br>'

        if queries:
            query_num: int = 0
            for query in queries:
                query_num += 1
                if query.strip():
                    query_result: Any = await conn.fetch(query) if isinstance(conn, asyncpg.Connection) else await conn.fetch_all(query)

                    num_of_rows: int = len(
                        query_result) if query_result else 0
                    if query_result:
                        columns: list[str] = list(query_result[0].keys())
                        num_of_columns: int = len(columns)
                    else:
                        columns = []
                        num_of_columns = 0

                    response += f"<h5>Query #{query_num} [({num_of_rows} rows) * ({num_of_columns} columns)]</h5>"
                    html_content: str = ""
                    if query_result:
                        # 開始HTML表格
                        html_content = "<table><tr>" + \
                            "".join(
                                f"<th>{col}</th>" for col in columns) + "</tr>"
                        for record in query_result:
                            record: dict[Any, Any] = dict(record)
                            record_values: list[Any] = list(record.values())
                            row: str = "".join(
                                f"<td>{(record_v if record_v is not None else 'null')}</td>" for record_v in record_values)
                            html_content += f"<tr>{row}</tr>"
                        html_content += "</table>"
                    else:
                        html_content = "<blockquote><strong>No results.</strong></blockquote>"
                    response += html_content + "<br>"
    except Exception as e:
        raise e
    finally:
        await drop_database(db_type, version, db_name)
        await conn.disconnect() if isinstance(conn, databases.Database) else await conn.close()

    return response
