import uuid
import asyncpg
import sqlparse
import databases

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

# 構建資料庫連接字串的函數
async def build_database_url(db_type: str, version: str, db_name: str) -> str:
    version_key = version.replace('.', '')  # 移除版本中的點
    if db_type == "mysql":
        return f"mysql+aiomysql://root:secret@mysql{version_key}/{db_name}"
    elif db_type == "postgres":
        return f"postgresql://postgres:secret@postgres{version_key}/{db_name}"
    else:
        raise ValueError("Unsupported database type")
    
# 解析多個 SQL 查詢的函數
async def parse_queries(full_query: str) -> list:
    parsed = sqlparse.split(full_query)
    return [query.strip() for query in parsed if query.strip()]

async def drop_database(db_type: str, version: str, db_name: str):
    admin_db_url = await build_database_url(db_type, version, "master" if db_type == "mssql" else "mysql" if db_type == "mysql" else "postgres")

    if db_type == "postgres":
        conn = await asyncpg.connect(admin_db_url)
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