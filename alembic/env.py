from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.db import get_database_url
from backend.app.models import Base
import backend.ingestion.models  # noqa: F401 -- registers the generic ingestion tables onto Base.metadata for autogenerate
import backend.release.models  # noqa: F401 -- registers the release-evaluation history table onto Base.metadata for autogenerate
import backend.alerts.models  # noqa: F401 -- registers the alerts table onto Base.metadata for autogenerate
import backend.review.models  # noqa: F401 -- registers the attribution_reviews table onto Base.metadata for autogenerate
import backend.auth.models  # noqa: F401 -- registers users/organizations/memberships/projects onto Base.metadata for autogenerate

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
