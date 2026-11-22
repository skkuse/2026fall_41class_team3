"""인증 코드 메일 발송. api를 import하지 않으므로 실패는 EmailSendError로 알리고, 상태 코드 변환은 라우트가 한다."""
import logging
import os
import smtplib
from email.message import EmailMessage

from flask import current_app
logger = logging.getLogger(__name__)

class EmailSendError(Exception):
    pass


SUBJECT = "[학교 커뮤니티] 이메일 인증 코드"
# 메일 본문 문구는 팀 확정 전 임시. 코드 유효 시간은 분 단위로 표시한다.
BODY = "인증 코드: {code}\n이 코드는 {minutes}분 동안 유효합니다.\n본인이 요청하지 않았다면 이 메일을 무시하세요."


def send_verification_email(email: str, code: str, ttl_sec: int) -> None:
    if current_app.debug and not os.environ.get("SMTP_HOST"):
        logger.warning("[DEV 메일 우회] to=%s code=%s (유효 %d초)", email, code, ttl_sec)
        return

    msg = EmailMessage()
    msg["Subject"] = SUBJECT
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = email
    msg.set_content(BODY.format(code=code, minutes=max(1, ttl_sec // 60)))
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=10) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    except (smtplib.SMTPException, OSError, KeyError) as e:
        raise EmailSendError(str(e)) from e