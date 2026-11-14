"""DB 모듈 공용 도구: 시각 문자열, 이메일 암호화."""
import base64
import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TIME_FMT = "%Y-%m-%dT%H:%M:%SZ"


def now() -> str:
    """UTC ISO-8601 문자열. DB의 모든 시각은 이 형식이라 문자열 비교로 대소를 판단할 수 있다."""
    return datetime.now(timezone.utc).strftime(TIME_FMT)


def shift(ts: str, **delta) -> str:
    """시각 문자열에 timedelta 인자(days=, minutes= 등)를 더한다."""
    base = datetime.strptime(ts, TIME_FMT) if "T" in ts else datetime.strptime(ts, "%Y-%m-%d")
    return (base + timedelta(**delta)).strftime(TIME_FMT)


def normalize_keyword(keyword: str) -> str:
    """비교용 키워드: 앞뒤 공백 제거, 연속 공백 하나로, 영문 소문자."""
    return re.sub(r"\s+", " ", keyword).strip().lower()


def _secret() -> bytes:
    """환경변수 DB_SECRET_KEY (base64, 32바이트). 코드·DB에 넣지 않는다 (3.6.3)."""
    raw = os.environ.get("DB_SECRET_KEY")
    if not raw:
        raise RuntimeError("DB_SECRET_KEY 환경변수가 없다")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("DB_SECRET_KEY는 32바이트여야 한다")
    return key


def email_hash(email: str) -> str:
    """조회용 식별값. 같은 이메일은 항상 같은 값."""
    return hmac.new(_secret(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


def encrypt_email(email: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_secret()).encrypt(nonce, email.strip().lower().encode(), None)


def decrypt_email(blob: bytes) -> str:
    return AESGCM(_secret()).decrypt(blob[:12], blob[12:], None).decode()
