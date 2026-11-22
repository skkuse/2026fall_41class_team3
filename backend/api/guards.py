"""로그인 상태 확인: 세션 쿠키에서 사용자를 찾아 g.user에 채우는 데코레이터와 세션 발급, 삭제.

세션 쿠키에는 user_id만 포함(Flask가 SECRET_KEY 서명으로 검증). id, department_id, email_addr 제외 사용자 정보는 user_id 기준 DB 검색
g.user는 로그인 상태면 AuthUser, 아닌 경우 None.
"""
from dataclasses import dataclass
from functools import wraps

from flask import current_app, g, session

from api.errors import ApiError
from db.user import get_user_by_id

SESSION_KEY = "user_id"


@dataclass(frozen=True)
class AuthUser:
    id: int
    email: str
    department_id: int | None


def auth_user_from_row(row) -> AuthUser:
    """DB의 사용자 행(dict 형태)을 AuthUser로 바꾼다. 필요한 컬럼만 남기고 나머지는 버린다."""
    return AuthUser(id=row["id"], email=row["email"], department_id=row["department_id"])


def login_session(user_id: int) -> None:
    """로그인 성공 시 세션 쿠키를 발급한다. 기존 세션 내용은 비우고 user_id만 담는다."""
    session.clear()
    session[SESSION_KEY] = user_id
    session.permanent = True            # 수명은 PERMANENT_SESSION_LIFETIME


def logout_session() -> None:
    session.clear()


def dev_fake_user() -> AuthUser | None:
    """개발 중에만: app.config["DEV_FAKE_USER_ID"]가 있고 debug일 때 그 사용자로 취급한다."""
    fake_id = current_app.config.get("DEV_FAKE_USER_ID")
    if not (current_app.debug and fake_id):
        return None
    row = get_user_by_id(fake_id)
    return auth_user_from_row(row) if row else None


def _load_user() -> AuthUser | None:
    user_id = session.get(SESSION_KEY)
    if user_id is None:
        return dev_fake_user()
    row = get_user_by_id(user_id)
    if row is None:                     # 삭제된 사용자의 쿠키는 버린다
        session.clear()
        return None
    return auth_user_from_row(row)


def optional_user(view):
    """로그인했으면 g.user = AuthUser, 아니면 None. 비로그인도 통과."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        g.user = _load_user()
        return view(*args, **kwargs)
    return wrapper


def require_user(view):
    """로그인 필수 엔드포인트 용. 비로그인이면 401 UNAUTHORIZED."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        g.user = _load_user()
        if g.user is None:
            raise ApiError(401, "UNAUTHORIZED", "이메일 인증이 필요합니다.")
        return view(*args, **kwargs)
    return wrapper