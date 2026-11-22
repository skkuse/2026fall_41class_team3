"""로그인 인증 코드 (로그인 파트 backend/api/auth가 부르는 함수).

발송할 때마다 email_code에 새 행을 추가하고, 조회는 그 이메일의 가장 최근 행만 본다.
이전 코드는 최신 행에 가려져 자동으로 무효가 된다. 이메일 원문은 저장하지 않는다(email_hash만).
반환하는 시각은 UTC datetime (api/auth/codes.py가 datetime으로 비교한다).
"""
from datetime import datetime

from sqlalchemy import select

from .engine import session_scope
from .models import EmailCode
from .util import email_hash, from_dt, now, to_dt


def _latest(s, email: str) -> EmailCode | None:
    return s.scalar(select(EmailCode).where(EmailCode.email_hash == email_hash(email))
                    .order_by(EmailCode.code_id.desc()).limit(1))


def get_code(email: str) -> dict | None:
    """가장 최근 코드 행. 한 번도 보낸 적 없으면 None."""
    with session_scope() as s:
        c = _latest(s, email)
        if c is None:
            return None
        return {"email": email, "code_hash": c.code_hash, "expires_at": to_dt(c.expires_at),
                "sent_at": to_dt(c.sent_at), "used_at": to_dt(c.used_at), "attempts": c.attempts,
                "send_count": c.send_count, "window_started_at": to_dt(c.window_started_at)}


def upsert_code(email: str, code_hash: str, expires_at: datetime, sent_at: datetime,
                send_count: int, window_started_at: datetime) -> None:
    """새 코드를 기록한다. 이름은 로그인 코드에 맞췄고, 실제로는 덮어쓰지 않고 새 행을 추가한다."""
    with session_scope() as s:
        s.add(EmailCode(email_hash=email_hash(email), code_hash=code_hash, expires_at=from_dt(expires_at),
                        sent_at=from_dt(sent_at), attempts=0, send_count=send_count,
                        window_started_at=from_dt(window_started_at)))


def increment_attempts(email: str) -> int:
    """최신 코드의 틀린 횟수를 1 늘리고 늘어난 값을 돌려준다. 코드가 없으면 0."""
    with session_scope() as s:
        c = _latest(s, email)
        if c is None:
            return 0
        c.attempts += 1
        return c.attempts


def mark_code_used(email: str) -> None:
    """최신 코드를 사용 처리한다 (같은 코드로 다시 로그인하지 못하게)."""
    with session_scope() as s:
        c = _latest(s, email)
        if c is not None and c.used_at is None:
            c.used_at = now()
