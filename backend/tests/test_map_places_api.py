"""api/map_places.py. 앞부분은 db.likes 를 메모리 가짜로 바꾼 테스트, 뒷부분은 임시 DB 로 한 바퀴 확인"""
import base64
import os
import pathlib
import sys

import pytest
from flask import Flask

os.environ.setdefault("DB_SECRET_KEY", base64.b64encode(b"k" * 32).decode())
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from api import guards, map_places  # noqa: E402
from api.errors import ApiError, register_error_handlers  # noqa: E402
from db.errors import DbError  # noqa: E402
from services import map_settings  # noqa: E402

NATURAL = "자연과학"
HUMANITIES = "인문사회"


def url(place_id):
    return f"http://place.map.kakao.com/{place_id}"


def body(place_id="111", **overrides):
    data = {"place_url": url(place_id), "campus": NATURAL}
    data.update(overrides)
    return data


# --- validate_like_input ------------------------------------------------------
def test_validate_returns_refined_values():
    assert map_places.validate_like_input("111", url(111), "  맛집  ", NATURAL) == (url(111), "맛집", NATURAL)
    assert map_places.validate_like_input("111", "https://place.map.kakao.com/111", None, HUMANITIES) == (
        "https://place.map.kakao.com/111", None, HUMANITIES)


@pytest.mark.parametrize("memo", ["", "   ", "\n"])
def test_validate_blank_memo_becomes_none(memo):
    assert map_places.validate_like_input("111", url(111), memo, NATURAL)[1] is None


def test_validate_memo_length_limit():
    ok = "가" * map_settings.MEMO_MAX_LEN
    assert map_places.validate_like_input("111", url(111), ok, NATURAL)[1] == ok
    with pytest.raises(ApiError):
        map_places.validate_like_input("111", url(111), ok + "가", NATURAL)


@pytest.mark.parametrize("args", [
    ("abc", url("abc"), None, NATURAL),                                # place_id 가 숫자가 아님
    ("", url(""), None, NATURAL),
    ("12a", url("12a"), None, NATURAL),
    ("１２３", url("１２３"), None, NATURAL),                           # 전각 숫자
    ("1" * 21, url("1" * 21), None, NATURAL),                          # 너무 긴 id
    ("111", url(222), None, NATURAL),                                  # 다른 장소의 url
    ("111", "http://place.map.kakao.com/111/", None, NATURAL),
    ("111", "http://place.map.kakao.com/111?x=1", None, NATURAL),
    ("111", "http://evil.com/111", None, NATURAL),
    ("111", "ftp://place.map.kakao.com/111", None, NATURAL),
    ("111", None, None, NATURAL),
    ("111", 111, None, NATURAL),
    ("111", url(111), 123, NATURAL),                                   # memo 가 문자열이 아님
    ("111", url(111), ["a"], NATURAL),
    ("111", url(111), None, "서울"),                                   # 없는 캠퍼스
    ("111", url(111), None, None),
    ("111", url(111), None, ["자연과학"]),
])
def test_validate_rejects_bad_input(args):
    with pytest.raises(ApiError) as exc:
        map_places.validate_like_input(*args)
    assert (exc.value.status, exc.value.code) == (422, "INVALID_REQUEST")


# --- RateLimiter ---------------------------------------------------------------
def test_rate_limiter_blocks_after_limit_and_recovers():
    limiter = map_places.RateLimiter(3, 60)
    assert [limiter.allow("u", now=t) for t in (0, 1, 2)] == [True, True, True]
    assert limiter.allow("u", now=3) is False
    assert limiter.allow("u", now=59.9) is False
    assert limiter.allow("u", now=60) is True             # 첫 요청(0초)이 구간 밖으로 나감


def test_rate_limiter_blocked_requests_are_not_recorded():
    limiter = map_places.RateLimiter(1, 10)
    assert limiter.allow("u", now=0) is True
    assert [limiter.allow("u", now=t) for t in (1, 5, 9)] == [False] * 3
    assert limiter.allow("u", now=10) is True              # 막힌 요청 때문에 풀리는 시각이 늦춰지지 않음


def test_rate_limiter_counts_each_key_separately():
    limiter = map_places.RateLimiter(1, 60)
    assert limiter.allow(1, now=0) and limiter.allow(2, now=0)
    assert not limiter.allow(1, now=1)


# --- 가짜 db.likes -------------------------------------------------------------
class FakeLikes:
    """db.likes 와 같은 규칙을 메모리에서 흉내 낸다 (이미 있으면 memo 만 교체, campus 유지)"""

    def __init__(self):
        self.rows = {}                                   # (user_id, place_id) -> dict, 입력 순서 유지

    def insert_like(self, user_id, place_id, place_url, campus, memo=None):
        key = (user_id, place_id)
        if key in self.rows:
            self.rows[key]["memo"] = memo
            return False
        self.rows[key] = {"place_id": place_id, "place_url": place_url, "campus": campus, "memo": memo,
                          "created_at": "t", "user_id": user_id}
        return True

    def delete_like(self, user_id, place_id):
        return self.rows.pop((user_id, place_id), None) is not None

    def count_user_likes(self, user_id):
        return sum(1 for u, _ in self.rows if u == user_id)

    def get_liked_place_ids(self, user_id, place_ids):
        return {p for p in place_ids if (user_id, p) in self.rows}

    def list_user_likes(self, user_id, campus=None):
        mine = [r for (u, _), r in self.rows.items() if u == user_id and campus in (None, r["campus"])]
        return list(reversed(mine))                      # 최신순


@pytest.fixture
def fake(monkeypatch):
    likes = FakeLikes()
    for name in ("insert_like", "delete_like", "count_user_likes", "get_liked_place_ids"):
        monkeypatch.setattr(map_places, name, getattr(likes, name))
    monkeypatch.setattr(map_places, "list_user_likes", likes.list_user_likes)
    return likes


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    map_places.rate_limiter.clear()
    yield
    map_places.rate_limiter.clear()


def make_app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", TESTING=True)
    register_error_handlers(app)
    app.register_blueprint(map_places.bp)
    return app


def login(client, user_id):
    with client.session_transaction() as sess:
        sess[guards.SESSION_KEY] = user_id


@pytest.fixture
def client(fake, monkeypatch):
    monkeypatch.setattr(guards, "get_user_by_id",
                        lambda uid: {"id": uid, "email": f"u{uid}@skku.edu", "department_id": None})
    client = make_app().test_client()
    login(client, 1)
    return client


def put(client, place_id="111", **overrides):
    return client.put(f"/api/places/{place_id}/like", json=body(place_id, **overrides))


# --- 인증 ----------------------------------------------------------------------
@pytest.mark.parametrize("method, path", [
    ("put", "/api/places/111/like"), ("delete", "/api/places/111/like"), ("get", "/api/me/place-likes"),
])
def test_requires_login(fake, method, path):
    res = getattr(make_app().test_client(), method)(path, json=body())
    assert res.status_code == 401 and res.get_json()["code"] == "UNAUTHORIZED"
    assert fake.rows == {}


# --- PUT -----------------------------------------------------------------------
def test_put_creates_like(client, fake):
    res = put(client, memo="  맛집  ")
    assert res.status_code == 200
    assert res.get_json() == {"place_id": "111", "created": True, "memo": "맛집"}
    assert fake.rows[(1, "111")]["campus"] == NATURAL and fake.rows[(1, "111")]["memo"] == "맛집"


def test_put_again_replaces_memo_and_keeps_campus(client, fake):
    put(client, memo="처음")
    res = put(client, memo="바꿈", campus=HUMANITIES)
    assert res.get_json() == {"place_id": "111", "created": False, "memo": "바꿈"}
    assert fake.rows[(1, "111")]["memo"] == "바꿈" and fake.rows[(1, "111")]["campus"] == NATURAL
    res = put(client)                                    # memo 를 생략하면 기존 메모도 지움
    assert res.get_json() == {"place_id": "111", "created": False, "memo": None}
    assert fake.rows[(1, "111")]["memo"] is None


@pytest.mark.parametrize("overrides", [
    {"place_url": url(222)}, {"place_url": None}, {"campus": "서울"}, {"campus": None}, {"memo": "가" * 31}, {"memo": 5},
])
def test_put_rejects_bad_body(client, fake, overrides):
    res = put(client, **overrides)
    assert res.status_code == 422 and res.get_json()["code"] == "INVALID_REQUEST"
    assert fake.rows == {}


@pytest.mark.parametrize("kwargs", [
    {"data": "not json", "content_type": "application/json"}, {"json": [1, 2]}, {"json": "text"}, {},
])
def test_put_rejects_non_object_body(client, fake, kwargs):
    res = client.put("/api/places/111/like", **kwargs)
    assert res.status_code == 422
    assert fake.rows == {}


def test_put_rejects_bad_place_id_in_path(client, fake):
    res = client.put("/api/places/abc/like", json=body("abc"))
    assert res.status_code == 422 and fake.rows == {}


# --- DELETE --------------------------------------------------------------------
def test_delete_like(client, fake):
    put(client)
    assert client.delete("/api/places/111/like").get_json() == {"place_id": "111", "deleted": True}
    assert fake.rows == {}
    res = client.delete("/api/places/111/like")          # 없는 좋아요도 정상 응답
    assert res.status_code == 200 and res.get_json() == {"place_id": "111", "deleted": False}


def test_delete_only_touches_own_like(client, fake):
    other = make_app().test_client()
    login(other, 2)
    other.put("/api/places/111/like", json=body())
    assert client.delete("/api/places/111/like").get_json()["deleted"] is False
    assert (2, "111") in fake.rows


def test_delete_rejects_bad_place_id(client):
    assert client.delete("/api/places/abc/like").status_code == 422


# --- GET -----------------------------------------------------------------------
def test_get_my_place_likes_newest_first_with_fields(client, fake):
    put(client, "111", memo="메모")
    put(client, "222", campus=HUMANITIES)
    res = client.get("/api/me/place-likes")
    assert res.status_code == 200
    assert res.get_json() == {"items": [
        {"place_id": "222", "place_url": url(222), "memo": None, "campus": HUMANITIES},
        {"place_id": "111", "place_url": url(111), "memo": "메모", "campus": NATURAL},
    ]}


def test_get_my_place_likes_filters_by_campus_and_user(client, fake):
    put(client, "111", campus=NATURAL)
    put(client, "222", campus=HUMANITIES)
    fake.insert_like(2, "333", url(333), NATURAL)
    ids = lambda res: [i["place_id"] for i in res.get_json()["items"]]
    assert ids(client.get("/api/me/place-likes?campus=" + NATURAL)) == ["111"]
    assert ids(client.get("/api/me/place-likes?campus=" + HUMANITIES)) == ["222"]
    assert ids(client.get("/api/me/place-likes")) == ["222", "111"]


@pytest.mark.parametrize("query", ["?campus=서울", "?campus="])
def test_get_my_place_likes_rejects_bad_campus(client, query):
    res = client.get("/api/me/place-likes" + query)
    assert res.status_code == 422 and res.get_json()["code"] == "INVALID_REQUEST"


# --- 사용자당 상한 ----------------------------------------------------------------
def fill(fake, user_id, count):
    for i in range(count):
        fake.insert_like(user_id, str(1000 + i), url(1000 + i), NATURAL)


def test_cap_blocks_new_like_but_not_existing_one(client, fake):
    fill(fake, 1, map_settings.LIKE_CAP_PER_USER)
    res = put(client, "999")
    assert res.status_code == 400 and res.get_json()["code"] == "LIKE_LIMIT_EXCEEDED"
    assert (1, "999") not in fake.rows
    res = put(client, "1000", memo="메모만 수정")            # 이미 누른 장소는 상한에서도 수정 가능
    assert res.status_code == 200 and res.get_json()["created"] is False
    assert fake.rows[(1, "1000")]["memo"] == "메모만 수정"


def test_cap_does_not_apply_to_delete_or_other_users(client, fake):
    fill(fake, 1, map_settings.LIKE_CAP_PER_USER)
    assert client.delete("/api/places/1000/like").status_code == 200
    assert put(client, "999").status_code == 200             # 99개가 되어 새로 누를 수 있음
    fill(fake, 2, 5)
    other = make_app().test_client()
    login(other, 2)
    assert other.put("/api/places/999/like", json=body("999")).status_code == 200


# --- 분당 횟수 -------------------------------------------------------------------
def test_rate_limit_counts_put_and_delete_together(client, fake):
    limit = map_settings.LIKE_RATE_PER_MIN
    for i in range(limit):
        res = put(client, "111") if i % 2 == 0 else client.delete("/api/places/111/like")
        assert res.status_code == 200
    for res in (put(client, "111"), client.delete("/api/places/111/like")):
        assert res.status_code == 429 and res.get_json()["code"] == "RATE_LIMITED"
    assert client.get("/api/me/place-likes").status_code == 200          # 목록 조회는 세지 않음


def test_rate_limit_is_per_user(client, fake):
    for _ in range(map_settings.LIKE_RATE_PER_MIN):
        put(client)
    assert put(client).status_code == 429
    other = make_app().test_client()
    login(other, 2)
    assert other.put("/api/places/111/like", json=body()).status_code == 200


def test_invalid_requests_do_not_use_up_the_rate_limit(client, fake):
    for _ in range(map_settings.LIKE_RATE_PER_MIN + 5):
        assert put(client, campus="서울").status_code == 422
    assert put(client).status_code == 200


# --- DB 오류 ---------------------------------------------------------------------
def test_db_error_becomes_503(client, monkeypatch):
    def locked(*args, **kwargs):
        raise DbError("locked")

    monkeypatch.setattr(map_places, "insert_like", locked)
    res = put(client)
    assert res.status_code == 503 and res.get_json()["code"] == "DB_ERROR"


def test_get_list_db_error_becomes_503(client, monkeypatch):
    def locked(*args, **kwargs):
        raise DbError("locked")

    monkeypatch.setattr(map_places, "list_user_likes", locked)
    assert client.get("/api/me/place-likes").status_code == 503


# --- 임시 DB 로 한 바퀴 (SQLAlchemy 가 없으면 건너뜀) -----------------------------------
@pytest.fixture
def real_client(tmp_path):
    pytest.importorskip("sqlalchemy")
    from db import configure, init_db, make_engine
    from db.user import create_user
    engine = make_engine(str(tmp_path / "t.db"))
    init_db(engine)
    configure(engine)
    client = make_app().test_client()
    login(client, create_user("a@skku.edu")["id"])
    yield client
    engine.dispose()


def test_real_db_round_trip(real_client):
    res = real_client.put("/api/places/111/like", json=body(memo="메모"))
    assert res.get_json() == {"place_id": "111", "created": True, "memo": "메모"}
    assert real_client.get("/api/me/place-likes").get_json() == {"items": [
        {"place_id": "111", "place_url": url(111), "memo": "메모", "campus": NATURAL}]}
    assert real_client.delete("/api/places/111/like").get_json() == {"place_id": "111", "deleted": True}
    assert real_client.get("/api/me/place-likes").get_json() == {"items": []}
    assert real_client.delete("/api/places/111/like").get_json()["deleted"] is False


def test_real_db_put_again_replaces_memo_keeps_campus(real_client):
    real_client.put("/api/places/111/like", json=body(memo="처음", campus=NATURAL))
    res = real_client.put("/api/places/111/like", json=body(campus=HUMANITIES))     # memo 생략, campus 다름
    assert res.get_json() == {"place_id": "111", "created": False, "memo": None}
    item = real_client.get("/api/me/place-likes").get_json()["items"][0]
    assert item["memo"] is None and item["campus"] == NATURAL


def test_real_db_cap(real_client):
    for i in range(map_settings.LIKE_CAP_PER_USER):
        map_places.rate_limiter.clear()                      # 상한 확인이 목적이므로 분당 제한은 비운다
        assert real_client.put(f"/api/places/{i + 1}/like", json=body(str(i + 1))).status_code == 200
    map_places.rate_limiter.clear()
    assert real_client.put("/api/places/99999/like", json=body("99999")).status_code == 400
    map_places.rate_limiter.clear()
    assert real_client.put("/api/places/1/like", json=body("1", memo="수정")).status_code == 200
