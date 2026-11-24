"""좋아요 조회. db.likes 를 감싸서 DB 오류를 규칙대로 처리"""

import logging
from db.likes import like_stats, list_likes_by_user

logger = logging.getLogger(__name__)


def get_like_info(user_id, place_ids) -> dict | None:
    """후보 장소별 {place_id: {"count": 개수, "liked_by_me": bool}} 반환. 좋아요 없는 장소는 count 0

    user_id 가 None 이면 liked_by_me 는 전부 False. DB 오류면 예외 대신 None 을 반환, search_places에서 정렬 없이 API 순서대로 처리
    """
    ids = [str(p) for p in place_ids]
    try:
        return like_stats(ids, user_id)
    except Exception:
        logger.exception("조회 실패")
        return None


def list_user_likes(user_id, campus=None) -> list[dict]:
    """개인 좋아요 목록. 항목: {place_id, place_url, memo, campus, created_at}

    DB 오류는 그대로 올린다 (API는 503, tools는 안내 문구로 처리)
    """
    return list_likes_by_user(user_id, campus)
