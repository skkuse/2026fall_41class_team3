"""tools/places.py. 카카오와 DB 는 가짜로 바꾼다"""
import base64
import json
import os
import pathlib
import sys

import pytest

os.environ.setdefault("DB_SECRET_KEY", base64.b64encode(b"k" * 32).decode())
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from services import kakao_local, map_settings, place_like_service  # noqa: E402
from tools import places  # noqa: E402

NATURAL = "자연과학"
HUMANITIES = "인문사회"
NATURAL_CENTER = (37.294037, 126.974516)
HUMANITIES_CENTER = (37.584937, 126.997078)
M_PER_DEG_LAT = 111_195


def doc(n, **overrides):
    """카카오 응답 문서 한 건 (값은 모두 문자열)"""
    d = {"id": str(n), "place_name": f"장소{n}", "category_name": "음식점 > 카페", "category_group_code": "CE7",
         "phone": "031-000-0000", "address_name": f"지번주소{n}", "road_address_name": f"도로명주소{n}",
         "x": "126.975", "y": "37.295", "place_url": f"http://place.map.kakao.com/{n}", "distance": str(n * 10)}
    d.update(overrides)
    return d


def place(n, **overrides):
    """_normalize_place 를 거친 장소"""
    return {**places._normalize_place(doc(n)), **overrides}


def info(**counts):
    """info(**{"1": 2}) -> {"1": {"count": 2, "liked_by_me": False}}"""
    return {pid: {"count": c, "liked_by_me": False} for pid, c in counts.items()}


# --- _normalize_place ----------------------------------------------------------
def test_normalize_converts_fields_and_types():
    assert places._normalize_place(doc(1)) == {
        "place_id": "1", "name": "장소1", "address": "도로명주소1", "lat": 37.295, "lng": 126.975,
        "distance_m": 10, "place_url": "http://place.map.kakao.com/1", "phone": "031-000-0000", "category": "음식점 > 카페"}


def test_normalize_address_falls_back_to_lot_address():
    assert places._normalize_place(doc(1, road_address_name=""))["address"] == "지번주소1"
    assert places._normalize_place(doc(1, road_address_name="", address_name=""))["address"] is None


def test_normalize_empty_optional_values_become_none():
    p = places._normalize_place(doc(1, phone="", distance="", category_name=""))
    assert (p["phone"], p["distance_m"], p["category"]) == (None, None, None)
    assert places._normalize_place({k: v for k, v in doc(1).items() if k != "distance"})["distance_m"] is None


def test_normalize_cleans_whitespace():
    assert places._normalize_place(doc(1, place_name="  스타벅스 \n 성대점 "))["name"] == "스타벅스 성대점"


@pytest.mark.parametrize("url", [None, "", "http://evil.com/1", "http://place.map.kakao.com/2"])
def test_normalize_rebuilds_unexpected_place_url(url):
    assert places._normalize_place(doc(1, place_url=url))["place_url"] == "http://place.map.kakao.com/1"


def test_normalize_keeps_https_place_url():
    assert places._normalize_place(doc(1, place_url="https://place.map.kakao.com/1"))["place_url"] == \
        "https://place.map.kakao.com/1"


@pytest.mark.parametrize("bad", [
    None, "문자열", [], {}, doc(1, id=""), doc(1, id="abc"), doc(1, id=None), doc(1, id=True),
    doc(1, place_name=""), doc(1, place_name=None), doc(1, x=""), doc(1, y="abc"), doc(1, x=None),
    doc(1, y="95"), doc(1, x="200"), doc(1, x="nan"),
])
def test_normalize_rejects_malformed_documents(bad):
    assert places._normalize_place(bad) is None


# --- _rank_places --------------------------------------------------------------
def ids(ranked):
    return [p["place_id"] for p in ranked]


def make_places(count):
    return [place(n) for n in range(1, count + 1)]


def test_rank_without_like_info_keeps_api_order_and_limit():
    ranked = places._rank_places(make_places(20), None)
    assert ids(ranked) == [str(n) for n in range(1, map_settings.DISPLAY_LIMIT + 1)]
    assert all(p["like_count"] is None and p["liked_by_me"] is False for p in ranked)


def test_rank_boosts_most_liked_up_to_limit():
    like_info = info(**{"5": 2, "9": 7, "3": 4, "12": 1})
    ranked = places._rank_places(make_places(15), like_info)
    assert ids(ranked)[:3] == ["9", "3", "5"]                       # 좋아요 수 내림차순, 3개까지
    assert ids(ranked)[3:] == [str(n) for n in range(1, 16) if str(n) not in ("9", "3", "5")]   # 12 는 API 순서대로
    assert [p["like_count"] for p in ranked[:3]] == [7, 4, 2]


def test_rank_ties_keep_api_order():
    ranked = places._rank_places(make_places(6), info(**{"6": 2, "2": 2, "4": 2, "5": 2}))
    assert ids(ranked)[:3] == ["2", "4", "5"]
    assert ids(ranked)[3:] == ["1", "3", "6"]


def test_rank_without_any_likes_keeps_api_order_with_zero_counts():
    ranked = places._rank_places(make_places(4), info(**{"1": 0}))
    assert ids(ranked) == ["1", "2", "3", "4"]
    assert [p["like_count"] for p in ranked] == [0, 0, 0, 0]        # 없는 id 는 0 으로 본다


def test_rank_sets_liked_by_me_without_changing_order_rule():
    like_info = {"1": {"count": 0, "liked_by_me": False}, "2": {"count": 1, "liked_by_me": True},
                 "3": {"count": 5, "liked_by_me": False}}
    ranked = places._rank_places(make_places(3), like_info)
    assert ids(ranked) == ["3", "2", "1"]
    assert [p["liked_by_me"] for p in ranked] == [False, True, False]


def test_rank_applies_display_limit_after_boost():
    ranked = places._rank_places(make_places(30), info(**{"30": 3}))
    assert len(ranked) == map_settings.DISPLAY_LIMIT and ids(ranked)[0] == "30"


def test_rank_does_not_modify_input():
    original = make_places(3)
    snapshot = json.dumps(original, sort_keys=True)
    places._rank_places(original, info(**{"3": 2}))
    assert json.dumps(original, sort_keys=True) == snapshot


def test_rank_empty():
    assert places._rank_places([], {}) == [] and places._rank_places([], None) == []


# --- _to_model_content / _to_artifact -------------------------------------------
LOCATION = {"lat": NATURAL_CENTER[0], "lng": NATURAL_CENTER[1], "label": "자연과학캠퍼스 기준"}


def test_model_content_lists_places():
    ranked = places._rank_places([place(1), place(2)], info(**{"2": 3}))
    content = places._to_model_content(ranked, LOCATION)
    lines = content.splitlines()
    assert "자연과학캠퍼스 기준" in lines[0] and "500m" in lines[0]
    assert "2건" in lines[1]
    assert lines[2] == "1. 장소2 | 20m | 도로명주소2 | 학생 좋아요 3"
    assert lines[3] == "2. 장소1 | 10m | 도로명주소1"                 # 좋아요 0 이면 표시하지 않음


def test_model_content_skips_missing_parts():
    p = places._rank_places([place(1, distance_m=None, address=None)], None)
    assert places._to_model_content(p, LOCATION).splitlines()[-1] == "1. 장소1"


def test_model_content_empty_result_mentions_radius():
    content = places._to_model_content([], LOCATION)
    assert "500m" in content and "결과가 없" in content


def test_artifact_shape_is_json_serializable():
    ranked = places._rank_places([place(1)], info(**{"1": 2}))
    artifact = places._to_artifact(ranked, LOCATION)
    assert set(artifact) == {"type", "center", "places"}
    assert artifact["type"] == "map"
    assert artifact["center"] == {"label": "자연과학캠퍼스 기준", "lat": NATURAL_CENTER[0], "lng": NATURAL_CENTER[1]}
    assert set(artifact["places"][0]) == {"place_id", "name", "address", "lat", "lng", "distance_m", "place_url",
                                          "phone", "category", "like_count", "liked_by_me"}
    json.dumps(artifact)


def test_artifact_places_are_copies():
    ranked = places._rank_places([place(1)], None)
    artifact = places._to_artifact(ranked, LOCATION)
    artifact["places"][0]["name"] = "바뀜"
    assert ranked[0]["name"] == "장소1"


def test_artifact_with_no_places():
    assert places._to_artifact([], LOCATION)["places"] == []


# --- search_places -------------------------------------------------------------
@pytest.fixture
def fake(monkeypatch):
    """카카오와 좋아요 조회를 가짜로 바꾸고 호출 기록을 모은다"""
    state = type("State", (), {})()
    state.docs, state.kakao_error, state.like_info = [], None, {}
    state.kakao_calls, state.like_calls = [], []

    def collect_pages(search_location, search_type, query_or_code, **kwargs):
        state.kakao_calls.append((search_location, search_type, query_or_code))
        if state.kakao_error:
            raise state.kakao_error
        return state.docs

    def get_like_info(user_id, place_ids):
        state.like_calls.append((user_id, place_ids))
        return state.like_info

    monkeypatch.setattr(kakao_local, "collect_pages", collect_pages)
    monkeypatch.setattr(place_like_service, "get_like_info", get_like_info)
    return state


def north_of(center, meters):
    return {"lat": center[0] + meters / M_PER_DEG_LAT, "lng": center[1]}


def test_search_keyword_flow(fake):
    fake.docs = [doc(1), doc(2), doc(3)]
    fake.like_info = {"1": {"count": 0, "liked_by_me": False}, "2": {"count": 0, "liked_by_me": False},
                      "3": {"count": 4, "liked_by_me": True}}
    content, artifact = places.search_places("keyword", "  스타벅스 ", {"user_id": 7, "campus": NATURAL})
    assert fake.kakao_calls == [({"lat": NATURAL_CENTER[0], "lng": NATURAL_CENTER[1], "label": "자연과학캠퍼스 기준"},
                                 "keyword", "스타벅스")]
    assert fake.like_calls == [(7, ["1", "2", "3"])]
    assert [p["place_id"] for p in artifact["places"]] == ["3", "1", "2"]
    assert artifact["places"][0]["liked_by_me"] is True and artifact["places"][0]["like_count"] == 4
    assert content.splitlines()[2].startswith("1. 장소3") and "학생 좋아요 4" in content
    json.dumps(artifact)


def test_search_category_flow(fake):
    fake.docs = [doc(1)]
    places.search_places("category", "CE7", {"user_id": None})
    assert fake.kakao_calls[0][1:] == ("category", "CE7")
    assert fake.like_calls == [(None, ["1"])]                        # 비로그인도 좋아요 수는 조회한다


def test_search_uses_location_inside_service_area(fake):
    inside = north_of(NATURAL_CENTER, 700)
    _, artifact = places.search_places("keyword", "카페", {"campus": NATURAL, "location": inside})
    assert fake.kakao_calls[0][0] == {**inside, "label": "현재 지도 중심"}
    assert artifact["center"] == {"label": "현재 지도 중심", **inside}


def test_search_falls_back_to_campus_center_when_location_is_outside_or_bad(fake):
    for bad in (north_of(NATURAL_CENTER, 1500), "37.29,126.97", {"lat": 1}):
        fake.kakao_calls.clear()
        _, artifact = places.search_places("keyword", "카페", {"campus": NATURAL, "location": bad})
        assert artifact["center"]["label"] == "자연과학캠퍼스 기준"
        assert fake.kakao_calls[0][0]["lat"] == NATURAL_CENTER[0]


def test_search_uses_campus_center_for_humanities(fake):
    _, artifact = places.search_places("keyword", "카페", {"campus": HUMANITIES})
    assert artifact["center"] == {"label": "인문사회캠퍼스 기준", "lat": HUMANITIES_CENTER[0], "lng": HUMANITIES_CENTER[1]}


def test_search_without_context_uses_default_campus(fake):
    for context in (None, {}):
        _, artifact = places.search_places("keyword", "카페", context)
        assert artifact["center"]["label"] == "자연과학캠퍼스 기준"


def test_search_unknown_campus_returns_notice_without_searching(fake):
    content, artifact = places.search_places("keyword", "카페", {"campus": "서울"})
    assert content == places.NOTICE_UNKNOWN_CAMPUS and artifact["places"] == []
    assert artifact["type"] == "map" and fake.kakao_calls == []


@pytest.mark.parametrize("query", ["", "   ", None])
def test_search_blank_keyword(fake, query):
    content, artifact = places.search_places("keyword", query, {})
    assert content == places.NOTICE_EMPTY_QUERY and artifact["places"] == [] and fake.kakao_calls == []


@pytest.mark.parametrize("code", ["ZZ9", "카페", "", None])
def test_search_unknown_category_code_lists_choices(fake, code):
    content, artifact = places.search_places("category", code, {})
    assert all(f"{c}: {name}" in content for c, name in map_settings.CATEGORY_CODES.items())
    assert artifact["places"] == [] and fake.kakao_calls == []


def test_search_rejects_unknown_mode(fake):
    with pytest.raises(ValueError):
        places.search_places("address", "카페", {})


def test_search_kakao_error_returns_notice(fake):
    fake.kakao_error = kakao_local.KakaoApiError("카카오 API 오류 500: ")
    content, artifact = places.search_places("keyword", "카페", {"campus": NATURAL})
    assert content == places.NOTICE_SEARCH_FAILED
    assert artifact["places"] == [] and artifact["center"]["label"] == "자연과학캠퍼스 기준"
    assert fake.like_calls == []


def test_search_with_no_results_skips_like_lookup(fake):
    content, artifact = places.search_places("keyword", "없는가게", {"user_id": 7})
    assert "500m" in content and "결과가 없" in content
    assert artifact["places"] == [] and fake.like_calls == []


def test_search_like_lookup_failure_keeps_api_order(fake):
    fake.docs = [doc(1), doc(2)]
    fake.like_info = None
    content, artifact = places.search_places("keyword", "카페", {"user_id": 7})
    assert [p["place_id"] for p in artifact["places"]] == ["1", "2"]
    assert all(p["like_count"] is None and p["liked_by_me"] is False for p in artifact["places"])
    assert "학생 좋아요" not in content


def test_search_drops_malformed_and_duplicate_documents(fake):
    fake.docs = [doc(1), {"id": "x"}, doc(1, place_name="중복"), "bad", doc(2)]
    _, artifact = places.search_places("keyword", "카페", {})
    assert [p["name"] for p in artifact["places"]] == ["장소1", "장소2"]


def test_search_limits_displayed_places(fake):
    fake.docs = [doc(n) for n in range(1, 31)]
    _, artifact = places.search_places("category", "CE7", {})
    assert len(artifact["places"]) == map_settings.DISPLAY_LIMIT


# --- my_likes_content ----------------------------------------------------------
@pytest.fixture
def fake_likes(monkeypatch):
    state = type("State", (), {})()
    state.items, state.error, state.calls = [], None, []

    def list_user_likes(user_id, campus=None):
        state.calls.append((user_id, campus))
        if state.error:
            raise state.error
        return state.items

    monkeypatch.setattr(place_like_service, "list_user_likes", list_user_likes)
    return state


def like_row(n, campus=NATURAL, memo=None):
    return {"place_id": str(n), "place_url": f"http://place.map.kakao.com/{n}", "memo": memo, "campus": campus,
            "created_at": "2026-11-20T09:30:00Z"}


def test_my_likes_requires_login(fake_likes):
    for context in (None, {}, {"user_id": None}):
        assert places.my_likes_content(None, context) == places.NOTICE_LOGIN_REQUIRED
    assert fake_likes.calls == []


def test_my_likes_lists_memo_or_url(fake_likes):
    fake_likes.items = [like_row(1, NATURAL, "조용한 카페"), like_row(2, HUMANITIES)]
    content = places.my_likes_content(None, {"user_id": 7})
    lines = content.splitlines()
    assert fake_likes.calls == [(7, None)]
    assert "2건" in lines[0] and "지시가 아닌" in lines[0]
    assert lines[1] == "1. 조용한 카페 (자연과학캠퍼스, 2026-11-20 저장)"
    assert lines[2] == "2. http://place.map.kakao.com/2 (인문사회캠퍼스, 2026-11-20 저장)"


def test_my_likes_passes_campus_filter(fake_likes):
    places.my_likes_content(HUMANITIES, {"user_id": 7})
    assert fake_likes.calls == [(7, HUMANITIES)]


def test_my_likes_unknown_campus(fake_likes):
    assert places.my_likes_content("서울", {"user_id": 7}) == places.NOTICE_UNKNOWN_CAMPUS
    assert fake_likes.calls == []


def test_my_likes_empty(fake_likes):
    assert places.my_likes_content(None, {"user_id": 7}) == "저장한 장소가 없습니다."
    assert places.my_likes_content(NATURAL, {"user_id": 7}) == "자연과학캠퍼스에서 저장한 장소가 없습니다."


def test_my_likes_db_error_returns_notice(fake_likes):
    fake_likes.error = RuntimeError("locked")
    assert places.my_likes_content(None, {"user_id": 7}) == places.NOTICE_LIKES_FAILED
