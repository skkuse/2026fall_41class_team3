"""사용자·학과·관심 키워드·관심 게시판.

다른 파트가 요청한 함수: get_user_scope, list_departments, list_keyword_subscribers (공지·알림 파트),
키워드 CRUD (공지·알림 파트 5절). 사용자 식별자는 서버 세션에서 꺼내 넘긴다 (LLM 인자로 받지 않음).
"""
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError

from .engine import session_scope
from .models import (AppUser, Board, Department, Faculty, Interest, InterestKeyword, UserInterest,
                     t_user_board)
from .util import decrypt_email, normalize_keyword, now


def get_user_scope(user_id: int) -> dict | None:
    """{is_verified, dept_id, dept_name, faculty_id, college_name}. 없는 사용자면 None.

    app_user에는 인증한 사용자만 있으므로 행이 있으면 is_verified는 항상 True.
    """
    with session_scope() as s:
        row = s.execute(
            select(AppUser.user_id, Department.dept_id, Department.name, Faculty.faculty_id, Faculty.name)
            .outerjoin(Department, AppUser.dept_id == Department.dept_id)
            .outerjoin(Faculty, Department.faculty_id == Faculty.faculty_id)
            .where(AppUser.user_id == user_id)
        ).first()
    if row is None:
        return None
    return {"is_verified": True, "dept_id": row[1], "dept_name": row[2],
            "faculty_id": row[3], "college_name": row[4]}


def list_departments() -> list[dict]:
    """학과 전체와 소속 학부. 학부별 묶음은 호출하는 쪽에서 한다 (캘린더 /api/departments)."""
    with session_scope() as s:
        rows = s.execute(
            select(Department.dept_id, Department.name, Faculty.faculty_id, Faculty.name,
                   Department.campus, Board.list_url)
            .join(Faculty, Department.faculty_id == Faculty.faculty_id)
            .outerjoin(Board, (Board.dept_id == Department.dept_id) & (Board.scope == "DEPT"))
            .order_by(Faculty.name, Department.name)
        ).all()
    return [{"dept_id": r[0], "name": r[1], "faculty_id": r[2], "college_name": r[3],
             "campus": r[4], "board_url": r[5]} for r in rows]


# ---------- 관심 키워드 ----------

def _kw(k: InterestKeyword) -> dict:
    return {"keyword_id": k.keyword_id, "keyword": k.keyword,
            "keyword_norm": k.keyword_norm, "created_at": k.created_at}


def list_keywords(user_id: int) -> list[dict]:
    with session_scope() as s:
        rows = s.scalars(select(InterestKeyword).where(InterestKeyword.user_id == user_id)
                         .order_by(InterestKeyword.created_at)).all()
        return [_kw(k) for k in rows]


def add_keyword(user_id: int, keyword: str) -> dict | None:
    """새 키워드. 같은 사용자에게 같은 keyword_norm이 이미 있으면 None."""
    try:
        with session_scope() as s:
            k = InterestKeyword(user_id=user_id, keyword=keyword.strip(),
                                keyword_norm=normalize_keyword(keyword), created_at=now())
            s.add(k)
            s.flush()
            return _kw(k)
    except IntegrityError:
        return None


def update_keyword(user_id: int, keyword_id: int, new_keyword: str) -> dict | None:
    """없거나 바꾼 값이 다른 키워드와 겹치면 None. created_at을 갱신해 이후 공지부터 매칭한다."""
    try:
        with session_scope() as s:
            k = s.scalar(select(InterestKeyword).where(InterestKeyword.keyword_id == keyword_id,
                                                       InterestKeyword.user_id == user_id))
            if k is None:
                return None
            k.keyword, k.keyword_norm, k.created_at = new_keyword.strip(), normalize_keyword(new_keyword), now()
            s.flush()
            return _kw(k)
    except IntegrityError:
        return None


def delete_keyword(user_id: int, keyword_id: int) -> bool:
    with session_scope() as s:
        n = s.execute(delete(InterestKeyword).where(InterestKeyword.keyword_id == keyword_id,
                                                    InterestKeyword.user_id == user_id)).rowcount
    return n > 0


def set_keywords(user_id: int, keywords: list[str]) -> list[dict]:
    """키워드 전체를 이 목록으로 바꾼다 (가입 직후 등록, 설정 화면 저장). 남는 것은 created_at 유지."""
    wanted = {}
    for kw in keywords:
        norm = normalize_keyword(kw)
        if norm:
            wanted.setdefault(norm, kw.strip())
    with session_scope() as s:
        existing = {k.keyword_norm: k for k in s.scalars(
            select(InterestKeyword).where(InterestKeyword.user_id == user_id))}
        for norm, k in existing.items():
            if norm not in wanted:
                s.delete(k)
        t = now()
        for norm, kw in wanted.items():
            if norm not in existing:
                s.add(InterestKeyword(user_id=user_id, keyword=kw, keyword_norm=norm, created_at=t))
    return list_keywords(user_id)


# ---------- 관심 게시판 ----------

def list_user_boards(user_id: int) -> list[int]:
    with session_scope() as s:
        return list(s.scalars(select(t_user_board.c.board_id).where(t_user_board.c.user_id == user_id)))


def set_user_boards(user_id: int, board_ids: list[int]) -> list[int]:
    with session_scope() as s:
        s.execute(delete(t_user_board).where(t_user_board.c.user_id == user_id))
        if board_ids:
            s.execute(insert(t_user_board), [{"user_id": user_id, "board_id": b} for b in set(board_ids)])
    return list_user_boards(user_id)


def list_keyword_subscribers(board_id: int | None = None) -> list[dict]:
    """알림 배치용. 키워드가 1개 이상인 인증 사용자와 키워드 목록.

    키워드 = 직접 입력한 키워드 + 온보딩에서 고른 관심사의 이름 (11-22 결정, keyword_norm 기준 중복 제거).
    board_id를 주면 그 게시판을 관심 게시판으로 등록한 사용자만. 이메일은 복호화해서 준다.
    """
    with session_scope() as s:
        q = (select(AppUser, Department.name, Faculty.name)
             .outerjoin(Department, AppUser.dept_id == Department.dept_id)
             .outerjoin(Faculty, Department.faculty_id == Faculty.faculty_id)
             .where(or_(AppUser.user_id.in_(select(InterestKeyword.user_id)),
                        AppUser.user_id.in_(select(UserInterest.user_id)))))
        if board_id is not None:
            q = q.where(AppUser.user_id.in_(
                select(t_user_board.c.user_id).where(t_user_board.c.board_id == board_id)))
        users = s.execute(q).all()
        ids = [u.user_id for u, _, _ in users]
        kws: dict[int, list] = {i: [] for i in ids}
        for k in s.scalars(select(InterestKeyword).where(InterestKeyword.user_id.in_(ids))):
            kws[k.user_id].append({"keyword_norm": k.keyword_norm, "keyword": k.keyword,
                                   "created_at": k.created_at, "source": "KEYWORD"})
        for ui, name in s.execute(select(UserInterest, Interest.name)
                                  .join(Interest, UserInterest.interest_id == Interest.interest_id)
                                  .where(UserInterest.user_id.in_(ids))):
            norm = normalize_keyword(name)
            if all(k["keyword_norm"] != norm for k in kws[ui.user_id]):
                kws[ui.user_id].append({"keyword_norm": norm, "keyword": name,
                                        "created_at": ui.created_at, "source": "INTEREST"})
        return [{"user_id": u.user_id, "email": decrypt_email(u.email_enc), "dept_id": u.dept_id,
                 "dept_name": dname, "college_name": fname, "keywords": kws[u.user_id]}
                for u, dname, fname in users]


def count_users() -> int:
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(AppUser))
