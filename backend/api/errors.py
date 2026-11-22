"""API 공통 오류: ApiError 예외와 오류 응답 형식, Flask 오류 핸들러 등록.

오류 본문은 {code, message, **extra}. 상태 코드는 HTTP 상태로 전달.
"""
import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException

from db.errors import DbError

log = logging.getLogger(__name__)


class ApiError(Exception):
    """라우트와 헬퍼가 던지면 핸들러가 {code, message, **extra} 응답으로 바꾼다."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


def error_response(status: int, code: str, message: str, **extra):
    body = {"code": code, "message": message, **extra}
    return jsonify(body), status


_HTTP_CODES = {400: "INVALID_REQUEST", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return error_response(e.status, e.code, e.message, **e.extra)

    @app.errorhandler(DbError)
    def _db_error(e: DbError):
        log.exception("DB error")
        return error_response(503, "DB_ERROR", "일시적인 오류입니다. 잠시 후 다시 시도해 주세요.")

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        code = _HTTP_CODES.get(e.code, "HTTP_ERROR")
        return error_response(e.code or 500, code, e.description or "")

    @app.errorhandler(Exception)
    def _unexpected(e: Exception):
        log.exception("Unhandled error")
        return error_response(500, "INTERNAL_ERROR", "서버 오류가 발생했습니다.")