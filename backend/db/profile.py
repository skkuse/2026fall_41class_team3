"""학과·관심사 선택지와 온보딩 저장 (로그인 파트 backend/api/auth가 부르는 함수).

목록은 {id, name} 형식. 학과 id는 seed 데이터가 정하고 FE와 같은 값을 쓴다.
사용자가 고른 관심사의 이름은 알림 키워드로도 쓴다 (users.list_keyword_subscribers).
"""
from sqlalchemy import delete, func, select

from .engine import session_scope
from .models import AppUser, Department, Interest, UserInterest
from .user import _row
from .util import now


def list_departments() -> list[dict]:
    with session_scope() as s:
        return [{"id": d.dept_id, "name": d.name}
                for d in s.scalars(select(Department).order_by(Department.faculty_id, Department.dept_id))]


def list_interests() -> list[dict]:
    with session_scope() as s:
        return [{"id": i.interest_id, "name": i.name}
                for i in s.scalars(select(Interest).order_by(Interest.sort_order, Interest.interest_id))]


def department_exists(department_id: int) -> bool:
    with session_scope() as s:
        return s.get(Department, department_id) is not None


def get_department_name(department_id: int) -> str | None:
    with session_scope() as s:
        d = s.get(Department, department_id)
        return d.name if d else None


def interests_exist(interest_ids: list[int]) -> bool:
    """모두 있는 관심사면 True. 빈 목록도 True."""
    ids = set(interest_ids)
    if not ids:
        return True
    with session_scope() as s:
        n = s.scalar(select(func.count()).select_from(Interest).where(Interest.interest_id.in_(ids)))
        return n == len(ids)


def list_user_interest_ids(user_id: int) -> list[int]:
    with session_scope() as s:
        return list(s.scalars(select(UserInterest.interest_id).where(UserInterest.user_id == user_id)
                              .order_by(UserInterest.interest_id)))


def save_profile(user_id: int, department_id: int, interest_ids: list[int] | None) -> dict:
    """학과 저장 + 관심사 교체를 한 트랜잭션으로. interest_ids가 None이면 관심사는 그대로.

    남는 관심사는 created_at을 유지한다 (새로 고른 관심사는 그 뒤 공지부터 알림 매칭).
    """
    with session_scope() as s:
        u = s.get(AppUser, user_id)
        u.dept_id = department_id
        if interest_ids is not None:
            wanted = set(interest_ids)
            have = set(s.scalars(select(UserInterest.interest_id).where(UserInterest.user_id == user_id)))
            if have - wanted:
                s.execute(delete(UserInterest).where(UserInterest.user_id == user_id,
                                                     UserInterest.interest_id.in_(have - wanted)))
            t = now()
            s.add_all([UserInterest(user_id=user_id, interest_id=i, created_at=t) for i in wanted - have])
        s.flush()
        return _row(u)
