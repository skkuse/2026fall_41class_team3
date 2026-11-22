"""참조 데이터(단과대학·학과·게시판·관심사) 넣기. 지금은 프로토타입 (seed/prototype_reference.json).

    python -m backend.db.seed_data            # repo 루트에서, DB_PATH의 DB에 넣는다

이미 단과대학이 있으면 아무것도 하지 않는다. 크롤링해 본 뒤 공지·알림 파트와 값을 확정한다.
"""
import json
from pathlib import Path

from sqlalchemy import func, insert, select

from .engine import get_engine, init_db, session_scope
from .models import Board, Department, Faculty, Interest

PROTOTYPE = Path(__file__).with_name("seed") / "prototype_reference.json"
BOARD_COLS = ("board_id", "name", "scope", "faculty_id", "dept_id", "list_url", "allowed_host",
              "parser_type", "is_active")


def load_reference(path: Path = PROTOTYPE) -> bool:
    """넣었으면 True, 이미 있어서 건너뛰었으면 False."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    with session_scope() as s:
        if s.scalar(select(func.count()).select_from(Faculty)):
            return False
        s.execute(insert(Faculty), data["faculties"])
        s.execute(insert(Department), data["departments"])
        s.execute(insert(Board), [{k: b[k] for k in BOARD_COLS} for b in data["boards"]])
        s.execute(insert(Interest), data["interests"])
    return True


if __name__ == "__main__":
    init_db(get_engine())
    print("loaded" if load_reference() else "already loaded, skipped")
