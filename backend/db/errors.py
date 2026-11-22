"""DB 쪽 예외. api/errors.py가 DbError를 503 DB_ERROR 응답으로 바꾼다."""


class DbError(Exception):
    """DB를 일시적으로 쓸 수 없음 (잠금 시간 초과, 파일 접근 실패 등). 다시 시도하면 될 수 있는 오류."""
