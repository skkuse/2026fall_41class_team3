"""ORM class와 schema.sql로 만든 실제 테이블이 맞는지 확인한다."""
from sqlalchemy import inspect

from backend.db import init_db, make_engine
from backend.db.models import Base


def test_models_match_schema(tmp_path):
    engine = make_engine(str(tmp_path / "t.db"))
    init_db(engine)
    insp = inspect(engine)

    db_tables = set(insp.get_table_names())
    orm_tables = set(Base.metadata.tables)
    assert orm_tables == db_tables

    for name, table in Base.metadata.tables.items():
        db_cols = {c["name"]: c for c in insp.get_columns(name)}
        assert set(table.columns.keys()) == set(db_cols), name
        for col in table.columns:
            assert col.nullable == db_cols[col.name]["nullable"] or col.primary_key, f"{name}.{col.name}"
        db_pk = set(insp.get_pk_constraint(name)["constrained_columns"])
        assert {c.name for c in table.primary_key.columns} == db_pk, name
        db_fk = {(fk["constrained_columns"][0], fk["referred_table"]) for fk in insp.get_foreign_keys(name)}
        orm_fk = {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys}
        assert orm_fk == db_fk, name


def test_pragmas(tmp_path):
    engine = make_engine(str(tmp_path / "t.db"))
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
