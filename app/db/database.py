"""异步数据库连接管理（SQLAlchemy 2.x + asyncpg）。

仅承载基础连接池与 schema 初始化；具体 CRUD 在 repository。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.common.logger import get_logger

_log = get_logger(__name__)


class Base(DeclarativeBase):
    """ORM 基类。"""

    pass


class Database:
    """异步数据库管理器。"""

    def __init__(self, url: str, pool_size: int = 10, echo: bool = False) -> None:
        self._url = url
        self._pool_size = pool_size
        self._echo = echo
        self._engine: Optional[AsyncEngine] = None
        self._sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

    async def connect(self) -> None:
        if self._engine is not None:
            return
        self._engine = create_async_engine(
            self._url,
            pool_size=self._pool_size,
            echo=self._echo,
            future=True,
        )
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        _log.info("database connected url=%s", self._url)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None
            _log.info("database closed")

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Database not connected")
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError("Database not connected")
        return self._sessionmaker

    def session(self) -> AsyncSession:
        return self.sessionmaker()

    async def create_all(self) -> None:
        """初始化表结构（开发/小规模使用）。"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _log.info("database schema created")


_db: Optional[Database] = None


async def init_database(url: str, pool_size: int = 10, echo: bool = False) -> Database:
    global _db
    if _db is None:
        _db = Database(url=url, pool_size=pool_size, echo=echo)
        await _db.connect()
    return _db


def get_database() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_database() during startup.")
    return _db


async def close_database() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
