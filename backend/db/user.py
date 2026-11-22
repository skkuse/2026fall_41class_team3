"""로그인 사용자 (로그인 파트 backend/api가 부르는 함수).

반환 형식은 로그인 코드에 맞춘 {id, email, department_id}. 이메일은 DB에 암호문으로 두고 여기서 복호화한다.
사용자 레코드는 인증 코드 확인에 성공한 순간 만든다 (학과는 그 뒤 온보딩에서).
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .engine import session_scope
from .models import AppUser
from .util import decrypt_email, email_hash, encrypt_email, now


def _row(u: AppUser) -> dict:
    return {"id": u.user_id, "email": decrypt_email(u.email_enc), "department_id": u.dept_id}


def get_user_by_id(user_id: int) -> dict | None:
    with session_scope() as s:
        u = s.get(AppUser, user_id)
        return _row(u) if u else None


def get_user_by_email(email: str) -> dict | None:
    with session_scope() as s:
        u = s.scalar(select(AppUser).where(AppUser.email_hash == email_hash(email)))
        return _row(u) if u else None


def create_user(email: str) -> dict:
    """인증된 이메일로 사용자를 만든다. 동시에 두 요청이 들어와 이미 있으면 그 사용자를 돌려준다."""
    t = now()
    try:
        with session_scope() as s:
            u = AppUser(email_enc=encrypt_email(email), email_hash=email_hash(email),
                        verified_at=t, created_at=t, last_access_at=t)
            s.add(u)
            s.flush()
            return _row(u)
    except IntegrityError:
        return get_user_by_email(email)


def update_last_login(user_id: int) -> None:
    """마지막 접속 시각 (12개월 미접속 삭제 안내의 기준). 접속하면 삭제 예고도 취소된다."""
    with session_scope() as s:
        u = s.get(AppUser, user_id)
        if u is not None:
            u.last_access_at = now()
            u.deletion_notified_at = None
