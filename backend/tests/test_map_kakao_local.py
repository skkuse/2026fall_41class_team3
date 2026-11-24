"""services/kakao_local.py. HTTP 는 가짜로 대체하고, 실제 호출 테스트는 KAKAO_LIVE_TEST=1 일 때만 실행 (환경변수 또는 backend/.env)"""
import os
import pathlib
import sys

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")      # KAKAO_LIVE_TEST 를 건너뛸지 판단하기 전에 읽어야 하므로 맨 위에서 호출

from services import kakao_local, map_settings  # noqa: E402
from services.kakao_local import KakaoApiError  # noqa: E402

LOCATION = {"lat": 37.294037, "lng": 126.974516}
KEY = "test-key-1234"
BAD_JSON = object()


def doc(n):
    """카카오 응답 문서 한 건 (값은 모두 문자열)"""
    return {"id": str(n), "place_name": f"장소{n}", "x": "126.97", "y": "37.29", "distance": str(n * 10),
            "place_url": f"http://place.map.kakao.com/{n}"}


class FakeResponse:
    def __init__(self, body=None, status=200):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is BAD_JSON:
            raise ValueError("not json")
        return self._body


def page_body(docs, is_end=True):
    return {"documents": docs, "meta": {"is_end": is_end, "total_count": len(docs)}}


@pytest.fixture
def fake_get(monkeypatch):
    """requests.get 을 대체한다. fake_get.responses 에 응답(또는 예외)을 순서대로 넣고, fake_get.calls 로 호출을 확인"""
    monkeypatch.setenv("KAKAO_REST_API_KEY", KEY)

    class Fake:
        calls = []
        responses = []

        def __call__(self, url, params=None, headers=None, timeout=None):
            self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    fake = Fake()
    fake.calls, fake.responses = [], []
    monkeypatch.setattr(kakao_local.requests, "get", fake)
    return fake


# --- fetch_places_page: 요청 ---------------------------------------------------
def test_keyword_request(fake_get):
    fake_get.responses = [FakeResponse(page_body([doc(1)]))]
    kakao_local.fetch_places_page(LOCATION, "keyword", " 맛집 ")
    call = fake_get.calls[0]
    assert call["url"] == "https://dapi.kakao.com/v2/local/search/keyword.json"
    assert call["headers"] == {"Authorization": f"KakaoAK {KEY}"}
    assert call["timeout"] == kakao_local.TIMEOUT_SEC
    assert call["params"] == {"x": LOCATION["lng"], "y": LOCATION["lat"], "radius": 500, "page": 1,
                              "size": 15, "sort": "distance", "query": "맛집"}


def test_category_request(fake_get):
    fake_get.responses = [FakeResponse(page_body([]))]
    kakao_local.fetch_places_page(LOCATION, "category", "CE7", radius=300, page=2, size=10, sort="accuracy")
    call = fake_get.calls[0]
    assert call["url"] == "https://dapi.kakao.com/v2/local/search/category.json"
    assert call["params"] == {"x": LOCATION["lng"], "y": LOCATION["lat"], "radius": 300, "page": 2,
                              "size": 10, "sort": "accuracy", "category_group_code": "CE7"}
    assert "query" not in call["params"]


# --- fetch_places_page: 응답 ---------------------------------------------------
def test_returns_documents_and_is_end(fake_get):
    fake_get.responses = [FakeResponse(page_body([doc(1), doc(2)], is_end=False))]
    result = kakao_local.fetch_places_page(LOCATION, "keyword", "카페")
    assert result == {"documents": [doc(1), doc(2)], "is_end": False}


def test_missing_meta_is_treated_as_end(fake_get):
    fake_get.responses = [FakeResponse({"documents": [doc(1)]})]
    assert kakao_local.fetch_places_page(LOCATION, "keyword", "카페")["is_end"] is True


# --- fetch_places_page: 실패 ---------------------------------------------------
def test_missing_key(fake_get, monkeypatch):
    monkeypatch.delenv("KAKAO_REST_API_KEY")
    with pytest.raises(KakaoApiError, match="KAKAO_REST_API_KEY"):
        kakao_local.fetch_places_page(LOCATION, "keyword", "카페")
    assert fake_get.calls == []


def test_http_error_includes_status_and_message(fake_get):
    body = {"errorType": "NotAuthorizedError", "message": "App disabled OPEN_MAP_AND_LOCAL service."}
    fake_get.responses = [FakeResponse(body, status=403)]
    with pytest.raises(KakaoApiError, match="403.*OPEN_MAP_AND_LOCAL") as exc:
        kakao_local.fetch_places_page(LOCATION, "keyword", "카페")
    assert KEY not in str(exc.value)


def test_http_error_with_non_json_body(fake_get):
    fake_get.responses = [FakeResponse(BAD_JSON, status=502)]
    with pytest.raises(KakaoApiError, match="502"):
        kakao_local.fetch_places_page(LOCATION, "keyword", "카페")


@pytest.mark.parametrize("error", [requests.Timeout("timed out"), requests.ConnectionError("down")])
def test_network_error(fake_get, error):
    fake_get.responses = [error]
    with pytest.raises(KakaoApiError, match="요청 실패") as exc:
        kakao_local.fetch_places_page(LOCATION, "keyword", "카페")
    assert KEY not in str(exc.value)


@pytest.mark.parametrize("body", [BAD_JSON, [], {"meta": {}}, {"documents": "x"}])
def test_bad_response_body(fake_get, body):
    fake_get.responses = [FakeResponse(body)]
    with pytest.raises(KakaoApiError):
        kakao_local.fetch_places_page(LOCATION, "keyword", "카페")


# --- fetch_places_page: 잘못된 인자 ---------------------------------------------
@pytest.mark.parametrize("kwargs", [
    {"search_location": None},
    {"search_location": {"lat": 37.29}},
    {"search_location": {"lat": "37.29", "lng": "126.97"}},
    {"search_type": "address"},
    {"query_or_code": ""},
    {"query_or_code": "   "},
    {"query_or_code": None},
    {"search_type": "category", "query_or_code": "ZZ9"},
    {"search_type": "category", "query_or_code": "카페"},
    {"radius": -1},
    {"radius": 20_001},
    {"radius": 500.5},
    {"radius": True},
    {"page": 0},
    {"page": 46},
    {"size": 0},
    {"size": 16},
    {"sort": "popular"},
])
def test_invalid_arguments(fake_get, kwargs):
    args = {"search_location": LOCATION, "search_type": "keyword", "query_or_code": "카페"}
    args.update(kwargs)
    with pytest.raises(ValueError):
        kakao_local.fetch_places_page(**args)
    assert fake_get.calls == []


def test_every_category_code_is_accepted(fake_get):
    for code in map_settings.CATEGORY_CODES:
        fake_get.responses.append(FakeResponse(page_body([])))
        kakao_local.fetch_places_page(LOCATION, "category", code)
    assert [c["params"]["category_group_code"] for c in fake_get.calls] == list(map_settings.CATEGORY_CODES)


# --- collect_pages -------------------------------------------------------------
def test_collect_pages_default_fetches_two_pages(fake_get):
    fake_get.responses = [FakeResponse(page_body([doc(1), doc(2)], is_end=False)),
                          FakeResponse(page_body([doc(3)], is_end=False))]
    docs = kakao_local.collect_pages(LOCATION, "keyword", "카페")
    assert [d["id"] for d in docs] == ["1", "2", "3"]
    assert [c["params"]["page"] for c in fake_get.calls] == [1, 2]
    assert all(c["params"]["size"] == map_settings.PAGE_SIZE for c in fake_get.calls)


def test_collect_pages_stops_at_last_page(fake_get):
    fake_get.responses = [FakeResponse(page_body([doc(1)], is_end=True))]
    assert len(kakao_local.collect_pages(LOCATION, "keyword", "카페")) == 1
    assert len(fake_get.calls) == 1


def test_collect_pages_respects_max_pages(fake_get):
    fake_get.responses = [FakeResponse(page_body([doc(i)], is_end=False)) for i in range(1, 4)]
    assert len(kakao_local.collect_pages(LOCATION, "keyword", "카페", max_pages=3)) == 3
    fake_get.calls.clear()
    fake_get.responses = [FakeResponse(page_body([doc(1)], is_end=False))]
    kakao_local.collect_pages(LOCATION, "keyword", "카페", max_pages=1)
    assert len(fake_get.calls) == 1


def test_collect_pages_passes_options(fake_get):
    fake_get.responses = [FakeResponse(page_body([]))]
    kakao_local.collect_pages(LOCATION, "category", "FD6", radius=300, sort="accuracy")
    params = fake_get.calls[0]["params"]
    assert (params["category_group_code"], params["radius"], params["sort"]) == ("FD6", 300, "accuracy")


def test_collect_pages_first_page_error_propagates(fake_get):
    fake_get.responses = [FakeResponse({}, status=500)]
    with pytest.raises(KakaoApiError, match="500"):
        kakao_local.collect_pages(LOCATION, "keyword", "카페")


def test_collect_pages_later_page_error_keeps_earlier_results(fake_get):
    fake_get.responses = [FakeResponse(page_body([doc(1)], is_end=False)), FakeResponse({}, status=500)]
    assert [d["id"] for d in kakao_local.collect_pages(LOCATION, "keyword", "카페")] == ["1"]


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, None])
def test_collect_pages_invalid_max_pages(fake_get, bad):
    with pytest.raises(ValueError):
        kakao_local.collect_pages(LOCATION, "keyword", "카페", max_pages=bad)


# --- 실제 호출 (KAKAO_LIVE_TEST=1 일 때만) -------------------------------------
LIVE = pytest.mark.skipif(os.environ.get("KAKAO_LIVE_TEST") != "1",
                          reason="실제 호출은 KAKAO_LIVE_TEST=1 일 때만 실행 (환경변수 또는 backend/.env)")


@pytest.fixture
def live_key():
    if not os.environ.get("KAKAO_REST_API_KEY"):
        pytest.skip("backend/.env 에 KAKAO_REST_API_KEY 없음")


@LIVE
@pytest.mark.parametrize("search_type, query_or_code", [("keyword", "카페"), ("category", "CE7")])
def test_live_search(live_key, search_type, query_or_code):
    docs = kakao_local.collect_pages(LOCATION, search_type, query_or_code)
    assert isinstance(docs, list) and len(docs) <= map_settings.MAX_CANDIDATES
    for d in docs:
        assert {"id", "place_name", "x", "y", "distance", "place_url"} <= set(d)
        assert int(d["distance"]) <= map_settings.SEARCH_RADIUS_M