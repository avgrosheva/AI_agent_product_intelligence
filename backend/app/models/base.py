from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for every application table (DATA_MODEL.md).

    Deliberately holds no ground-truth columns or tables: everything mapped
    under this Base is loaded into the application's Postgres database and
    is fair game for the API/analytics layer to read. Ground truth lives
    only in validation_ground_truth.parquet (DATA_MODEL.md S8) and is never
    represented here.
    """
