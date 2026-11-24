"""지도 좋아요 엔드포인트: 등록(PUT), 취소(DELETE), 내 목록(GET)"""

import re
import time
from collections import deque
from threading import Lock

from flask import Blueprint, g, jsonify, request

from api.errors import ApiError
from api.guards import require_user
from db.likes import count_user_likes, delete_like, get_liked_place_ids, insert_like
from services import campuses, map_settings
from services.place_like_service import list_user_likes

bp = Blueprint("map_places", __name__, url_prefix="/api")

PLACE_ID_PATTERN = re.compile(r"[0-9]{1,20}")


# --- 요청 제한 --------------------------------------------------------------
class RateLimiter:
    """사용자별 요청 시각을 서버 메모리에 기록해 구간 안 횟수를 센다. 재시작하면 초기화되고, 서버 프로세스 하나를 전제로 한다"""

    def __init__(self, limit: int, window_sec: float):
        self.limit = limit
        self.window_sec = window_sec
        self._hits: dict = {}
        self._lock = Lock()

    def allow(self, key, now: float | None = None) -> bool:
        """허용하면 요청을 기록하고 True, 한도를 넘으면 기록 없이 False"""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window_sec:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter(map_settings.LIKE_RATE_PER_MIN, map_settings.LIKE_RATE_WINDOW_SEC)


# --- 보조 함수 ---------------------------------------------------------------
def _invalid(message: str) -> ApiError:
    return ApiError(422, "INVALID_REQUEST", message)


def validate_place_id(place_id) -> str:
    if not isinstance(place_id, str) or not PLACE_ID_PATTERN.fullmatch(place_id):
        raise _invalid("place_id 형식이 올바르지 않습니다.")
    return place_id


def validate_like_input(place_id, place_url, memo, campus) -> tuple[str, str | None, str]:
    """PUT 입력 검사. (place_url, memo, campus) 를 정리해서 반환하고, 틀리면 422

    memo 는 앞뒤 공백을 지우고 빈 문자열이면 None 으로 바꾼다
    """
    validate_place_id(place_id)
    if not isinstance(place_url, str) or place_url not in [p + place_id for p in map_settings.PLACE_URL_PREFIXES]:
        raise _invalid("place_url 형식이 올바르지 않습니다.")
    if memo is not None:
        if not isinstance(memo, str):
            raise _invalid("memo 는 문자열이어야 합니다.")
        memo = memo.strip() or None
        if memo is not None and len(memo) > map_settings.MEMO_MAX_LEN:
            raise _invalid(f"memo 는 {map_settings.MEMO_MAX_LEN}자 이하여야 합니다.")
    if not campuses.is_valid_campus_id(campus):
        raise _invalid("campus 값이 올바르지 않습니다.")
    return place_url, memo, campus


def check_like_limits(user_id: int, is_put: bool, place_id: str | None = None) -> None:
    """요청 제한 검사. 통과하면 None, 초과하면 ApiError

    분당 횟수(429)는 PUT, DELETE 합산. 사용자당 상한(400)은 PUT 에만 적용하고, 이미 누른 장소는 제외한다
    """
    if not rate_limiter.allow(user_id):
        raise ApiError(429, "RATE_LIMITED", "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    if is_put and count_user_likes(user_id) >= map_settings.LIKE_CAP_PER_USER:
        if place_id not in get_liked_place_ids(user_id, [place_id]):
            raise ApiError(400, "LIKE_LIMIT_EXCEEDED",
                           f"좋아요는 {map_settings.LIKE_CAP_PER_USER}개까지 저장할 수 있습니다.")


def _json_body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


# --- 엔드포인트 ----------------------------------------------------------------
@bp.put("/places/<place_id>/like")
@require_user
def put_place_like(place_id):
    """좋아요 등록. 이미 있으면 memo 만 보낸 값으로 교체한다 (생략하면 메모 삭제, campus 는 처음 값 유지)"""
    body = _json_body()
    place_url, memo, campus = validate_like_input(place_id, body.get("place_url"), body.get("memo"),
                                                  body.get("campus"))
    check_like_limits(g.user.id, True, place_id)
    created = insert_like(g.user.id, place_id, place_url, campus, memo)
    return jsonify(place_id=place_id, created=created, memo=memo)


@bp.delete("/places/<place_id>/like")
@require_user
def delete_place_like(place_id):
    """좋아요 취소. 없던 좋아요여도 오류 없이 deleted=false"""
    validate_place_id(place_id)
    check_like_limits(g.user.id, False)
    return jsonify(place_id=place_id, deleted=delete_like(g.user.id, place_id))


@bp.get("/me/place-likes")
@require_user
def get_my_place_likes():
    """내 좋아요 목록 (최신순). ?campus= 를 주면 그 캠퍼스에서 누른 것만"""
    campus = request.args.get("campus")
    if campus is not None and not campuses.is_valid_campus_id(campus):
        raise _invalid("campus 값이 올바르지 않습니다.")
    items = [{key: row[key] for key in ("place_id", "place_url", "memo", "campus")}
             for row in list_user_likes(g.user.id, campus)]
    return jsonify(items=items)
