"""services/place_like_service.py. 앞부분은 db.likes 를 가짜로 바꾼 테스트, 뒷부분은 임시 DB 로 실제 동작을 확인"""
import base64
import logging
import os
import pathlib
import sys

import pytest

os.environ.setdefault("DB_SECRET_KEY", base64.b64encode(b"k" * 32).decode())
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from db.errors import DbError  # noqa: E402
from services import place_like_service as service  # noqa: E402

NATURAL = "자연과학"
HUMANITIES = "인문사회"


def url(place_id):
    return f"http://place.map.kakao.com/{place_id}"


# --- db.likes 를 가짜로 바꾼 테스트 ----------------------------------------------
@pytest.fixture
def fake_stats(monkeypatch):
    """like_stats 를 대체하고 받은 인자를 기록한다"""
    calls = []

    def fake(place_ids, user_id=None):
        calls.append((place_ids, user_id))
        return {p: {"count": 1, "liked_by_me": user_id is not None} for p in place_ids}

    monkeypatch.setattr(service, "like_stats", fake)
    return calls


def test_get_like_info_converts_ids_to_str(fake_stats):
    info = service.get_like_info(7, [111, "222"])
    assert fake_stats == [(["111", "222"], 7)]
    assert info == {"111": {"count": 1, "liked_by_me": True}, "222": {"count": 1, "liked_by_me": True}}


def test_get_like_info_without_user(fake_stats):
    info = service.get_like_info(None, ["111"])
    assert fake_stats == [(["111"], None)]
    assert info == {"111": {"count": 1, "liked_by_me": False}}


@pytest.mark.parametrize("error", [DbError("locked"), RuntimeError("boom"), ValueError("bad")])
def test_get_like_info_returns_none_on_any_error(monkeypatch, caplog, error):
    def fail(place_ids, user_id=None):
        raise error

    monkeypatch.setattr(service, "like_stats", fail)
    with caplog.at_level(logging.ERROR):
        assert service.get_like_info(7, ["111"]) is None
    assert "좋아요 조회 실패" in caplog.text


def test_list_user_likes_passes_arguments_and_result(monkeypatch):
    rows = [{"place_id": "111", "place_url": url(111), "memo": None, "campus": NATURAL, "created_at": "t"}]
    calls = []
    monkeypatch.setattr(service, "list_likes_by_user", lambda user_id, campus=None: calls.append((user_id, campus)) or rows)
    assert service.list_user_likes(7) == rows
    assert service.list_user_likes(7, HUMANITIES) is rows
    assert calls == [(7, None), (7, HUMANITIES)]


def test_list_user_likes_raises_db_error(monkeypatch):
    def fail(user_id, campus=None):
        raise DbError("locked")

    monkeypatch.setattr(service, "list_likes_by_user", fail)
    with pytest.raises(DbError):
        service.list_user_likes(7)


# --- 임시 DB 테스트 (SQLAlchemy 가 없으면 건너뜀) ------------------------------------
@pytest.fixture
def real_db(tmp_path):
    pytest.importorskip("sqlalchemy")
    from db import configure, init_db, make_engine
    engine = make_engine(str(tmp_path / "t.db"))
    init_db(engine)
    configure(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def users(real_db):
    from db.user import create_user
    return create_user("a@skku.edu")["id"], create_user("b@skku.edu")["id"]


def like(user_id, place_id, campus=NATURAL, memo=None):
    from db.likes import insert_like
    assert insert_like(user_id, str(place_id), url(place_id), campus, memo) is True


def test_get_like_info_counts_and_flags(users):
    a, b = users
    like(a, 111)
    like(a, 222)
    like(b, 111)
    assert service.get_like_info(a, ["111", "222", "333"]) == {
        "111": {"count": 2, "liked_by_me": True},
        "222": {"count": 1, "liked_by_me": True},
        "333": {"count": 0, "liked_by_me": False},
    }
    assert service.get_like_info(b, ["111", "222"]) == {
        "111": {"count": 2, "liked_by_me": True},
        "222": {"count": 1, "liked_by_me": False},
    }


def test_get_like_info_without_user_and_int_ids(users):
    a, _ = users
    like(a, 111)
    assert service.get_like_info(None, [111, 222]) == {
        "111": {"count": 1, "liked_by_me": False},
        "222": {"count": 0, "liked_by_me": False},
    }
    assert service.get_like_info(a, []) == {}


def test_get_like_info_after_unlike(users):
    from db.likes import delete_like
    a, b = users
    like(a, 111)
    like(b, 111)
    assert delete_like(a, "111") is True
    assert service.get_like_info(a, ["111"]) == {"111": {"count": 1, "liked_by_me": False}}


def test_get_like_info_returns_none_when_db_is_unusable(real_db, monkeypatch):
    import db.likes

    def locked(*args, **kwargs):
        raise DbError("locked")

    monkeypatch.setattr(db.likes, "session_scope", locked)
    assert service.get_like_info(1, ["111"]) is None


def test_list_user_likes_newest_first_with_fields(users):
    from db.engine import session_scope
    from db.models import LikePlace
    a, b = users
    like(a, 111, NATURAL, "메모")
    like(a, 222, HUMANITIES)
    like(b, 333)
    with session_scope() as s:                      # 같은 초에 만들어지므로 저장 시각을 직접 구분한다
        s.get(LikePlace, (a, "111")).created_at = "2026-01-01T00:00:00Z"
        s.get(LikePlace, (a, "222")).created_at = "2026-02-01T00:00:00Z"
    items = service.list_user_likes(a)
    assert [i["place_id"] for i in items] == ["222", "111"]
    assert items[1] == {"place_id": "111", "place_url": url(111), "memo": "메모", "campus": NATURAL,
                        "created_at": "2026-01-01T00:00:00Z"}
    assert items[0]["memo"] is None


def test_list_user_likes_campus_filter_and_other_users(users):
    a, b = users
    like(a, 111, NATURAL)
    like(a, 222, HUMANITIES)
    like(b, 333, NATURAL)
    assert [i["place_id"] for i in service.list_user_likes(a, NATURAL)] == ["111"]
    assert [i["place_id"] for i in service.list_user_likes(a, HUMANITIES)] == ["222"]
    assert [i["place_id"] for i in service.list_user_likes(b)] == ["333"]
    assert service.list_user_likes(9999) == []
