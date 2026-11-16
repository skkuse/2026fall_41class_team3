"""인증 코드 생성·해시·검증과 발송 제한.

HTTP와 무관한 로직. 요청 객체는 쓰지 않고 DB는 get_code 조회만 수행. (저장·갱신은 호출하는 routes.py)
"""
import hashlib
import hmac
import math
import secrets
from datetime import datetime, timezone

from flask import current_app

from api.auth import settings as cfg
from api.errors import ApiError
from db.email_verification import get_code


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """DB에서 tzinfo 없이 읽힌 UTC 시각에 UTC를 붙인다."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# ---------------------------------------------------------------- 코드 생성·해시

def make_code() -> str:
    """CODE_LENGTH 자리 숫자 코드. random이 아니라 secrets를 쓴다(예측 불가)."""
    return "".join(secrets.choice("0123456789") for _ in range(cfg.CODE_LENGTH))


def hash_code(email: str, code: str) -> str:
    """HMAC-SHA256(SECRET_KEY, "email:code"). DB에는 평문 코드 대신 이 값만 저장한다."""
    key = current_app.config["SECRET_KEY"]
    if isinstance(key, str):
        key = key.encode()
    return hmac.new(key, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- 코드 검증

def verify_code(row: dict | None, code: str) -> bool:
    """DB 행과 입력 코드를 대조한다.

    맞으면 True, 틀리면 False. 틀린 횟수를 늘리는 일은 호출하는 쪽이 한다.
    코드가 없거나 만료·사용됨이면 410, 시도 횟수를 넘겼으면 429를 올린다.
    """
    if row is None:
        raise ApiError(410, "CODE_EXPIRED", "인증 코드를 먼저 요청해 주세요.")
    if row["used_at"] is not None or _as_utc(row["expires_at"]) <= utcnow():
        raise ApiError(410, "CODE_EXPIRED", "인증 코드가 만료되었습니다. 새 코드를 요청해 주세요.")
    if row["attempts"] >= cfg.MAX_ATTEMPTS:
        raise ApiError(429, "TOO_MANY_ATTEMPTS", "시도 횟수를 초과했습니다. 새 코드를 요청해 주세요.")
    # 길이가 같은 문자열끼리 상수 시간으로 비교한다 (타이밍 공격 방지)
    return hmac.compare_digest(hash_code(row["email"], code), row["code_hash"])


# ---------------------------------------------------------------- 발송 제한

def check_send_limits(email: str) -> tuple[int, datetime]:
    """발송 전에 호출한다. 한도를 넘으면 429 RATE_LIMITED(retry_after 포함).

    통과하면 이번 발송까지 포함한 (send_count, window_started_at)을 돌려준다.
    호출하는 쪽이 이 값을 upsert_code로 DB에 저장한다.

    - 재발송 간격: 마지막 발송(sent_at)으로부터 RESEND_COOLDOWN_SEC 안이면 거절
    - 횟수 제한: 구간(window_started_at부터 SEND_WINDOW_SEC) 안에서 SEND_LIMIT_PER_WINDOW번까지만 허용. 구간이 끝났으면 새 구간을 시작한다.
    """
    now = utcnow()
    row = get_code(email)
    if row is None:
        return 1, now

    # 1) 재발송 간격
    elapsed = (now - _as_utc(row["sent_at"])).total_seconds()
    if elapsed < cfg.RESEND_COOLDOWN_SEC:
        raise ApiError(429, "RATE_LIMITED", "잠시 후 다시 요청해 주세요.",
                       retry_after=math.ceil(cfg.RESEND_COOLDOWN_SEC - elapsed))

    # 2) 구간 안 발송 횟수
    if row["window_started_at"] is None:
        return 1, now                              # 구간 시작점이 없으면 새로 시작
    window_started_at = _as_utc(row["window_started_at"])
    if (now - window_started_at).total_seconds() >= cfg.SEND_WINDOW_SEC:
        return 1, now                              # 구간이 끝났으니 새로 시작
    if row["send_count"] >= cfg.SEND_LIMIT_PER_WINDOW:
        retry_after = math.ceil(cfg.SEND_WINDOW_SEC - (now - window_started_at).total_seconds())
        raise ApiError(429, "RATE_LIMITED", "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
                       retry_after=retry_after)
    return row["send_count"] + 1, window_started_at
