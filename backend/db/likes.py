"""장소 좋아요 (지도 파트 요청, 공유 Docs "지도 (11/12)" 탭).

delete_likes_of_user는 두지 않는다: 사용자 삭제 시 DB가 CASCADE로 지운다.
"""
from sqlalchemy import delete, func, select

from .engine import session_scope
from .models import LikePlace

KAKAO_PLACE = ("http://place.map.kakao.com/", "https://place.map.kakao.com/")


def _valid_url(place_id: str, place_url: str) -> bool:
    return place_url in (KAKAO_PLACE[0] + place_id, KAKAO_PLACE[1] + place_id)


def insert_like(user_id: int, place_id: str, place_url: str, campus: str, memo: str | None = None) -> bool:
    """새로 만들면 True. 이미 있으면 memo만 바꾸고 False. place_url이 형식에 안 맞으면 ValueError."""
    place_id = str(place_id)
    if not _valid_url(place_id, place_url):
        raise ValueError("place_url은 http(s)://place.map.kakao.com/{place_id} 형식이어야 한다")
    with session_scope() as s:
        like = s.get(LikePlace, (user_id, place_id))
        if like is not None:
            like.memo = memo
            return False
        s.add(LikePlace(user_id=user_id, place_id=place_id, place_url=place_url, campus=campus, memo=memo))
    return True


def delete_like(user_id: int, place_id: str) -> bool:
    """지운 행이 없어도 오류 없이 False."""
    with session_scope() as s:
        n = s.execute(delete(LikePlace).where(LikePlace.user_id == user_id,
                                              LikePlace.place_id == str(place_id))).rowcount
    return n > 0


def like_stats(place_ids: list[str], user_id: int | None = None) -> dict[str, dict]:
    """{place_id: {"count": n, "liked_by_me": bool}}. 좋아요 없는 장소도 count 0으로 포함."""
    ids = [str(p) for p in place_ids]
    out = {p: {"count": 0, "liked_by_me": False} for p in ids}
    if not ids:
        return out
    with session_scope() as s:
        for pid, n in s.execute(select(LikePlace.place_id, func.count())
                                .where(LikePlace.place_id.in_(ids)).group_by(LikePlace.place_id)):
            out[pid]["count"] = n
        if user_id is not None:
            for pid in s.scalars(select(LikePlace.place_id)
                                 .where(LikePlace.user_id == user_id, LikePlace.place_id.in_(ids))):
                out[pid]["liked_by_me"] = True
    return out


def count_likes_by_place_ids(place_ids: list[str]) -> dict[str, int]:
    return {p: v["count"] for p, v in like_stats(place_ids).items()}


def get_liked_place_ids(user_id: int, place_ids: list[str]) -> set[str]:
    return {p for p, v in like_stats(place_ids, user_id).items() if v["liked_by_me"]}


def count_user_likes(user_id: int) -> int:
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(LikePlace).where(LikePlace.user_id == user_id))


def list_likes_by_user(user_id: int, campus: str | None = None) -> list[dict]:
    with session_scope() as s:
        q = select(LikePlace).where(LikePlace.user_id == user_id)
        if campus is not None:
            q = q.where(LikePlace.campus == campus)
        return [{"place_id": l.place_id, "place_url": l.place_url, "campus": l.campus,
                 "memo": l.memo, "created_at": l.created_at}
                for l in s.scalars(q.order_by(LikePlace.created_at.desc()))]
