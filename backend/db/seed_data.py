"""참조 데이터(단과대학·학과·게시판·관심사) 넣기. 지금은 프로토타입 (seed/prototype_reference.json).

    python -m backend.db.seed_data            # repo 루트에서, DB_PATH의 DB에 맞춘다

같은 id끼리 맞춘다: 없으면 추가, 있으면 파일 값으로 갱신. 파일에 없는 행은 지우지 않는다
(사용자 등이 참조할 수 있어서). 그래서 seed 파일이 바뀌면 이미 만든 DB에 다시 돌려도 된다.
게시판의 크롤링 현황 열(실패 횟수, 마지막 성공, last_article_no)은 건드리지 않는다.
크롤링해 본 뒤 공지·알림 파트와 값을 확정한다.
"""
import json
from pathlib import Path

from .engine import get_engine, init_db, session_scope
from .models import Board, Department, Faculty, Interest

PROTOTYPE = Path(__file__).with_name("seed") / "prototype_reference.json"
COLS = {
    Faculty: ("faculty_id", "name"),
    Department: ("dept_id", "faculty_id", "name", "campus", "is_selectable"),
    Board: ("board_id", "name", "scope", "faculty_id", "dept_id", "list_url", "allowed_host", "parser_type",
            "is_active"),
    Interest: ("interest_id", "name", "sort_order"),
}
KEYS = {Faculty: "faculties", Department: "departments", Board: "boards", Interest: "interests"}


def load_reference(path: Path = PROTOTYPE) -> dict:
    """{테이블: (추가 수, 갱신 수)}. 바뀐 게 없으면 전부 (0, 0)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    with session_scope() as s:
        for model in (Faculty, Department, Board, Interest):      # FK 순서
            cols, pk = COLS[model], COLS[model][0]
            added = changed = 0
            for row in data[KEYS[model]]:
                obj = s.get(model, row[pk])
                if obj is None:
                    s.add(model(**{c: row.get(c) for c in cols}))
                    added += 1
                    continue
                diff = {c: row.get(c) for c in cols[1:] if getattr(obj, c) != row.get(c)}
                for c, v in diff.items():
                    setattr(obj, c, v)
                changed += bool(diff)
            s.flush()
            out[model.__tablename__] = (added, changed)
    return out


if __name__ == "__main__":
    init_db(get_engine())
    print(load_reference())
