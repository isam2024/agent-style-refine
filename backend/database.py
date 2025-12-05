import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from backend.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def run_migrations(conn):
    """Run any needed schema migrations."""
    # Add critique_json column to iterations if it doesn't exist
    try:
        await conn.execute(text(
            "ALTER TABLE iterations ADD COLUMN critique_json JSON"
        ))
        logger.info("Added critique_json column to iterations table")
    except Exception:
        # Column already exists
        pass

    # Add training_summary_json column to trained_styles if it doesn't exist
    try:
        await conn.execute(text(
            "ALTER TABLE trained_styles ADD COLUMN training_summary_json JSON"
        ))
        logger.info("Added training_summary_json column to trained_styles table")
    except Exception:
        # Column already exists
        pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Run migrations for schema updates
        await run_migrations(conn)


async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
