"""보존 기간 정리 batch 초안 (SRS 3.4.5).

    python -m backend.db.retention          # 하루 한 번 (cron 등)

- 대화·tool·검색 기록: 마지막 활동 30일 뒤 삭제 (대화 단위, 메시지·기록은 CASCADE)
- 익명 대화: 마지막 활동 1일 뒤 삭제 (SRS는 '세션 종료 시'. 브라우저 종료를 서버가 모르니 1일로 근사)
- 인증 코드 행: 발송 1일 뒤 삭제
- 사용자: 12개월 미접속이면 삭제 예고 메일 대상 -> 예고 30일 안에 안 들어오면 삭제
  (메일 발송은 알림 파트. 여기선 대상 목록과 표시만)
"""
from sqlalchemy import delete, select

from .engine import get_engine, init_db, session_scope
from .models import AppUser, EmailCode, Session
from .util import decrypt_email, now, shift

CONVERSATION_DAYS = 30
ANONYMOUS_DAYS = 1
EMAIL_CODE_DAYS = 1
INACTIVE_DAYS = 365
DELETE_GRACE_DAYS = 30


def purge_conversations(days: int = CONVERSATION_DAYS, anonymous_days: int = ANONYMOUS_DAYS) -> int:
    t = now()
    with session_scope() as s:
        n = s.execute(delete(Session).where(Session.updated_at < shift(t, days=-days))).rowcount
        n += s.execute(delete(Session).where(Session.user_id.is_(None),
                                             Session.updated_at < shift(t, days=-anonymous_days))).rowcount
    return n


def purge_email_codes(days: int = EMAIL_CODE_DAYS) -> int:
    with session_scope() as s:
        return s.execute(delete(EmailCode).where(EmailCode.sent_at < shift(now(), days=-days))).rowcount


def users_to_warn(days: int = INACTIVE_DAYS) -> list[dict]:
    """삭제 예고 메일을 보낼 사용자 [{id, email, last_access_at}] (아직 예고 안 한 사람만)."""
    with session_scope() as s:
        rows = s.scalars(select(AppUser).where(AppUser.last_access_at < shift(now(), days=-days),
                                               AppUser.deletion_notified_at.is_(None)))
        return [{"id": u.user_id, "email": decrypt_email(u.email_enc), "last_access_at": u.last_access_at}
                for u in rows]


def mark_warned(user_ids: list[int]) -> None:
    """예고 메일을 보낸 뒤 호출. 그 사이 로그인하면 user.update_last_login이 표시를 지운다."""
    t = now()
    with session_scope() as s:
        for u in s.scalars(select(AppUser).where(AppUser.user_id.in_(user_ids))):
            u.deletion_notified_at = t


def delete_warned_users(grace_days: int = DELETE_GRACE_DAYS) -> int:
    """예고 뒤 grace_days가 지나도록 안 들어온 사용자 삭제 (키워드·좋아요·대화 등 CASCADE)."""
    with session_scope() as s:
        return s.execute(delete(AppUser).where(AppUser.deletion_notified_at.is_not(None),
                                               AppUser.deletion_notified_at < shift(now(), days=-grace_days))
                         ).rowcount


def run_all() -> dict:
    """메일이 필요 없는 정리만 한다. 예고 메일은 users_to_warn -> 발송 -> mark_warned 순서로 따로."""
    return {"conversations": purge_conversations(), "email_codes": purge_email_codes(),
            "users_deleted": delete_warned_users(), "users_to_warn": len(users_to_warn())}


if __name__ == "__main__":
    init_db(get_engine())
    print(run_all())
