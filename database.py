import os

import aiosql
from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не найден в .env")


# Async-адаптер для Psycopg 3
queries = aiosql.from_path(
    "sql",
    "apsycopg",
    mandatory_parameters=False,
)


# Асинхронный пул PostgreSQL
pool = AsyncConnectionPool(
    conninfo=DATABASE_URL,
    min_size=5,
    max_size=20,
    open=False,
)


async def init_db():
    """Открыть пул и выполнить init.sql."""

    await pool.open()

    async with pool.connection() as conn:
        await queries.init_db(conn)
        await conn.commit()


async def close_db():
    """Закрыть пул."""

    await pool.close()