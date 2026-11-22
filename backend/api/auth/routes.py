"""로그인 흐름 엔드포인트: 코드 발송, 코드 확인(로그인), 로그아웃."""
import re
from datetime import timedelta

from flask import Blueprint, jsonify, request

from api.auth import settings as cfg
from api.auth.codes import (check_send_limits, hash_code, make_code, utcnow,
                            verify_code)
from api.auth.me import needs_onboarding, user_payload
from api.errors import ApiError
from api.guards import auth_user_from_row, login_session, logout_session
from db.email_verification import (get_code, increment_attempts, mark_code_used,
                                   upsert_code)
from db.user import create_user, get_user_by_email, update_last_login
from services.email_sender import EmailSendError, send_verification_email

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_STUDENT_ID_RE = re.compile(cfg.STUDENT_ID_PATTERN)


def build_email(body: dict) -> str:
    """요청 본문의 {student_id, domain}으로 이메일을 조립.

    domain은 FE가 보내는 도메인 코드(0, 1)이고, 실제 도메인은 settings.EMAIL_DOMAINS에서 추출.
    """
    student_id = body.get("student_id")
    if not isinstance(student_id, str):
        raise ApiError(422, "INVALID_REQUEST", "교내 ID를 입력해 주세요.")
    student_id = student_id.strip().lower()
    if not _STUDENT_ID_RE.fullmatch(student_id):
        raise ApiError(422, "INVALID_REQUEST", "교내 ID 형식이 올바르지 않습니다.")

    domain = body.get("domain")
    if isinstance(domain, bool) or not isinstance(domain, int) or domain not in cfg.EMAIL_DOMAINS:
        raise ApiError(422, "EMAIL_DOMAIN_NOT_ALLOWED", "허용되지 않는 이메일 도메인입니다.")
    return f"{student_id}@{cfg.EMAIL_DOMAINS[domain]}"


@bp.post("/email-code")
def post_email_code():
    """인증 코드를 만들어 메일로 보낸다. 요청은 {student_id, domain}이고, DB에는 코드의 해시만 저장한다."""
    body = request.get_json(silent=True) or {}
    email = build_email(body)

    # 한도를 넘으면 여기서 429. 통과하면 이번 발송을 포함한 구간 횟수와 구간 시작 시각을 받는다
    send_count, window_started_at = check_send_limits(email)

    code = make_code()
    now = utcnow()
    # 이메일당 행 하나: 재발송하면 새 행을 추가하고 최신 행만 참고
    upsert_code(email, hash_code(email, code),
                now + timedelta(seconds=cfg.CODE_TTL_SEC), now,
                send_count, window_started_at)
    try:
        send_verification_email(email, code, cfg.CODE_TTL_SEC)
    except EmailSendError:
        raise ApiError(502, "EMAIL_SEND_FAILED", "메일 전송 실패. 잠시 후 다시 시도해 주세요.")

    return jsonify(expires_in=cfg.CODE_TTL_SEC, resend_after=cfg.RESEND_COOLDOWN_SEC)


@bp.post("/verify")
def post_verify():
    """코드를 확인하고, 맞으면 사용자 생성 또는 조회 후 로그인 세션을 발급한다."""
    body = request.get_json(silent=True) or {}
    email = build_email(body)
    code = body.get("code")
    if not (isinstance(code, str) and code.isdigit() and len(code) == cfg.CODE_LENGTH):
        raise ApiError(422, "INVALID_REQUEST", f"인증 코드는 {cfg.CODE_LENGTH}자리 숫자입니다.")

    row = get_code(email)
    if not verify_code(row, code):          # 만료, 횟수 초과는 verify_code가 exception raise
        attempts = increment_attempts(email)
        raise ApiError(400, "INVALID_CODE", "인증 코드가 올바르지 않습니다.",
                       remaining_attempts=max(0, cfg.MAX_ATTEMPTS - attempts))

    mark_code_used(email)                   # 이미 로그인 완료된 계정에 대해 추가 로그인 세션 발급을 유도하는 replay 방어

    user_row = get_user_by_email(email) or create_user(email)
    update_last_login(user_row["id"])

    user = auth_user_from_row(user_row)
    login_session(user.id)                  # Set-Cookie: session=...
    return jsonify(user=user_payload(user), needs_onboarding=needs_onboarding(user))


@bp.post("/logout")
def post_logout():
    """세션 쿠키를 비운다. 이미 로그아웃 상태여도 204."""
    logout_session()
    return "", 204
