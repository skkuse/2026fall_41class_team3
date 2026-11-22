"""DB 연결. engine 하나를 만들고, 작업 단위마다 session을 연다.

- DB 파일 경로는 환경변수 DB_PATH (기본 data/app.db).
- 연결마다 외래키·WAL·busy_timeout을 켠다. 크롤러와 웹 서버가 같은 파일을 쓰기 때문.
- 테이블은 init_db()가 schema.sql로 만든다. ORM의 create_all은 쓰지 않는다 (trigger, 식 index 때문).
"""
import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from .errors import DbError

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def make_engine(db_path: str | None = None, read_only: bool = False) -> Engine:
    path = db_path or os.environ.get("DB_PATH", "data/app.db")
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    if read_only:
        # Agent·검색 경로용 (3.4.3: 질의응답 조회 경로는 읽기 전용)
        url = f"sqlite:///file:{Path(path).as_posix()}?mode=ro&uri=true"
    else:
        url = f"sqlite:///{path}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.execute("PRAGMA busy_timeout = 5000")
        if not read_only and path != ":memory:":
            cur.execute("PRAGMA journal_mode = WAL")
        cur.close()

    return engine


def init_db(engine: Engine) -> None:
    """빈 DB에 schema.sql을 실행한다. 이미 테이블이 있으면 아무것도 하지 않는다."""
    raw = engine.raw_connection()
    try:
        exists = raw.execute("SELECT 1 FROM sqlite_master WHERE name = 'app_user'").fetchone()
        if not exists:
            raw.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            raw.commit()
    finally:
        raw.close()


_engine: Engine | None = None
_Session: sessionmaker | None = None


def configure(engine: Engine) -> None:
    """기본 engine을 바꾼다 (테스트, 읽기 전용 연결 등)."""
    global _engine, _Session
    _engine = engine
    _Session = sessionmaker(engine, expire_on_commit=False)


def get_engine() -> Engine:
    if _engine is None:
        configure(make_engine())
    return _engine


@contextmanager
def session_scope(engine: Engine | None = None):
    """with session_scope() as s: ... 블록이 끝나면 commit, 예외면 rollback."""
    if engine is None:
        get_engine()
        maker = _Session
    else:
        maker = sessionmaker(engine, expire_on_commit=False)
    s: Session = maker()
    try:
        yield s
        s.commit()
    except OperationalError as e:       # 잠금 시간 초과 등 일시 오류 -> DbError (API는 503)
        s.rollback()
        raise DbError(str(e.orig)) from e
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
