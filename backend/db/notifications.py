"""알림 기록 (공지·알림 파트 요청 4절, 일정 알림과 공용).

발송 전에 PENDING으로 먼저 기록하고, 같은 사용자·같은 대상이 이미 있으면 기록하지 않는다 (중복 발송 방지).
"""
import json

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from .engine import session_scope
from .models import Notice, Notification
from .notices import _tag
from .util import now, shift

TARGET_COL = {"NOTICE": "notice_id", "EVENT": "schedule_id"}


def create_pending_notification(user_id: int, target_type: str, target_id: int,
                                matched_keywords: list[str] | None = None) -> int | None:
    """target_type은 "NOTICE" 또는 "EVENT". 이미 기록이 있으면 None."""
    kind = "KEYWORD_MATCH" if target_type == "NOTICE" else "EVENT_REMINDER"
    try:
        with session_scope() as s:
            n = Notification(user_id=user_id, kind=kind, created_at=now(),
                             matched_keywords=json.dumps(matched_keywords or [], ensure_ascii=False),
                             **{TARGET_COL[target_type]: target_id})
            s.add(n)
            s.flush()
            return n.notif_id
    except IntegrityError:
        return None


def mark_notification_sent(notification_id: int, sent_at: str | None = None) -> None:
    with session_scope() as s:
        n = s.get(Notification, notification_id)
        n.status, n.sent_at = "SENT", sent_at or now()
        n.attempt_count += 1


def mark_notification_failed(notification_id: int, error: str, permanent: bool) -> None:
    """permanent면 DEAD(재시도 안 함), 아니면 FAILED."""
    with session_scope() as s:
        n = s.get(Notification, notification_id)
        n.status, n.last_error = ("DEAD" if permanent else "FAILED"), error
        n.attempt_count += 1


def list_retryable_notifications(max_attempts: int = 3, stale_pending_minutes: int = 10) -> list[dict]:
    """FAILED이면서 시도 횟수가 max_attempts 미만인 것 + 오래 남은 PENDING (발송 중 프로세스가 죽은 경우)."""
    cutoff = shift(now(), minutes=-stale_pending_minutes)
    with session_scope() as s:
        rows = s.scalars(select(Notification).where(or_(
            (Notification.status == "FAILED") & (Notification.attempt_count < max_attempts),
            (Notification.status == "PENDING") & (Notification.created_at < cutoff)))).all()
        return [{"notification_id": n.notif_id, "user_id": n.user_id, "notice_id": n.notice_id,
                 "schedule_id": n.schedule_id, "attempt_count": n.attempt_count,
                 "matched_keywords": json.loads(n.matched_keywords or "[]")} for n in rows]


def list_user_notifications(user_id: int, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    """사용자 알림 기록 화면 (GET /api/me/notifications). 발송 완료(SENT)된 공지 알림만."""
    conds = [Notification.user_id == user_id, Notification.status == "SENT", Notification.notice_id.is_not(None)]
    with session_scope() as s:
        total = s.scalar(select(func.count()).select_from(Notification).where(*conds))
        rows = s.execute(select(Notification, Notice).join(Notice, Notification.notice_id == Notice.notice_id)
                         .where(*conds).order_by(Notification.sent_at.desc()).limit(limit).offset(offset)).all()
        return [{"notification_id": n.notif_id, "title": no.title, "category": no.category, "url": no.url,
                 "tags": [_tag(t) for t in no.notice_tag], "deadline": no.summary_deadline,
                 "matched_keywords": json.loads(n.matched_keywords or "[]"), "sent_at": n.sent_at}
                for n, no in rows], total
