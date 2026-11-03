"""Alembic environment: points migrations at our models and our DATABASE_URL."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.models import Base  # importing this registers every model

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The PostGIS image ships its own tables (spatial reference systems, the US
# "tiger" address geocoder, topology). They are not ours and autogenerate must
# never try to create or drop them.
POSTGIS_SCHEMAS = {"tiger", "tiger_data", "topology"}
POSTGIS_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns"}

# Our own tables, by name. Anything reflected from the database that is not in
# this set is somebody else's and is left alone.
OUR_TABLES = set(Base.metadata.tables.keys())


def include_object(obj, name, type_, reflected, compare_to):
    schema = getattr(obj, "schema", None)
    if schema in POSTGIS_SCHEMAS:
        return False

    if type_ == "table":
        if name in POSTGIS_TABLES:
            return False
        return name in OUR_TABLES

    # Only consider indexes/constraints that sit on one of our tables.
    table_name = getattr(getattr(obj, "table", None), "name", None)
    if table_name is not None and table_name not in OUR_TABLES:
        return False

    # GeoAlchemy2 manages its own spatial indexes.
    if type_ == "index" and name is not None and name.startswith("idx_"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        compare_type=True,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
