"""services/campuses.py, services/map_settings.py. 외부 서비스와 DB 를 쓰지 않는다."""
import json
import pathlib
import sys

import pytest

# 서버와 같은 방식(backend/ 를 기준으로 services.x 처럼 import)으로 불러온다.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from services import campuses, map_settings  # noqa: E402

NATURAL = "자연과학"
HUMANITIES = "인문사회"
NATURAL_CENTER = (37.294037, 126.974516)
HUMANITIES_CENTER = (37.584937, 126.997078)
M_PER_DEG_LAT = 111_195        # 위도 1도의 거리(m). 위도를 이만큼 옮겨서 원하는 거리의 점을 만든다


def north_of(center, meters):
    return {"lat": center[0] + meters / M_PER_DEG_LAT, "lng": center[1]}


# --- 실제 설정 파일 --------------------------------------------------------
def test_real_config_is_valid():
    loaded = campuses.load_campuses()
    # id 는 DB like_place.campus 의 CHECK 값과 같아야 한다
    assert set(loaded) == {NATURAL, HUMANITIES}
    assert loaded[NATURAL]["center"] == {"lat": NATURAL_CENTER[0], "lng": NATURAL_CENTER[1]}
    assert loaded[HUMANITIES]["center"] == {"lat": HUMANITIES_CENTER[0], "lng": HUMANITIES_CENTER[1]}
    assert all(c["service_radius_m"] == 1000 for c in loaded.values())
    assert [c["name"] for c in loaded.values()] == ["자연과학캠퍼스", "인문사회캠퍼스"]


def test_default_campus():
    default = campuses.get_default_campus()
    assert default["id"] == NATURAL
    default["name"] = "바꿔도 원본은 그대로"
    assert campuses.get_default_campus()["name"] == "자연과학캠퍼스"


# --- 설정 파일 검증 ---------------------------------------------------------
def write_config(tmp_path, items):
    path = tmp_path / "campuses.json"
    path.write_text(json.dumps({"campuses": items}, ensure_ascii=False), encoding="utf-8")
    return path


def campus_item(**overrides):
    item = {"id": "a", "name": "A캠퍼스", "center": {"lat": 37.0, "lng": 127.0}, "service_radius_m": 1000,
            "default": True}
    item.update(overrides)
    return item


@pytest.mark.parametrize("items, message", [
    ([], "campuses"),
    ([campus_item(), campus_item()], "중복"),
    ([campus_item(default=False)], "default"),
    ([campus_item(), campus_item(id="b")], "default"),
    ([campus_item(center={"lat": 95, "lng": 127})], "center"),
    ([campus_item(center={"lat": "37", "lng": 127})], "center"),
    ([campus_item(service_radius_m=0)], "service_radius_m"),
    ([campus_item(service_radius_m=True)], "service_radius_m"),
    ([campus_item(name="")], "name"),
    ([campus_item(default="yes")], "default"),
])
def test_load_campuses_rejects_bad_config(tmp_path, items, message):
    with pytest.raises(ValueError, match=message):
        campuses.load_campuses(write_config(tmp_path, items))


# --- 조회 ----------------------------------------------------------------
def test_is_valid_campus_id():
    assert campuses.is_valid_campus_id(NATURAL) and campuses.is_valid_campus_id(HUMANITIES)
    for bad in ("서울", "", None, 1, ["자연과학"]):
        assert not campuses.is_valid_campus_id(bad)


def test_get_campus_center():
    assert campuses.get_campus_center(NATURAL) == {"lat": NATURAL_CENTER[0], "lng": NATURAL_CENTER[1],
                                                   "name": "자연과학캠퍼스"}
    with pytest.raises(campuses.UnknownCampusError):
        campuses.get_campus_center("없는캠퍼스")


# --- 거리와 서비스 영역 -------------------------------------------------------
def test_distance_m():
    assert campuses.distance_m(*NATURAL_CENTER, *NATURAL_CENTER) == 0
    assert campuses.distance_m(37.0, 127.0, 38.0, 127.0) == pytest.approx(M_PER_DEG_LAT, abs=200)
    # 두 캠퍼스는 서로 약 32km
    assert 31_000 < campuses.distance_m(*NATURAL_CENTER, *HUMANITIES_CENTER) < 34_000


def test_is_within_service_area():
    assert campuses.is_within_service_area(*NATURAL_CENTER, NATURAL)
    point = north_of(NATURAL_CENTER, 900)
    assert campuses.is_within_service_area(point["lat"], point["lng"], NATURAL)
    point = north_of(NATURAL_CENTER, 1100)
    assert not campuses.is_within_service_area(point["lat"], point["lng"], NATURAL)
    # 다른 캠퍼스 중심은 영역 밖
    assert not campuses.is_within_service_area(*HUMANITIES_CENTER, NATURAL)


def test_is_within_service_area_bad_input():
    assert not campuses.is_within_service_area("a", 127, NATURAL)       # 좌표 형식 오류는 False
    assert not campuses.is_within_service_area(None, None, NATURAL)
    with pytest.raises(campuses.UnknownCampusError):
        campuses.is_within_service_area(*NATURAL_CENTER, "없는캠퍼스")


# --- 검색 기준 위치 --------------------------------------------------------
def test_resolve_without_location_uses_default_campus_center():
    loc = campuses.resolve_search_location()
    assert loc == {"lat": NATURAL_CENTER[0], "lng": NATURAL_CENTER[1], "label": "자연과학캠퍼스 기준"}


def test_resolve_with_campus_uses_that_center():
    loc = campuses.resolve_search_location(campus=HUMANITIES)
    assert loc == {"lat": HUMANITIES_CENTER[0], "lng": HUMANITIES_CENTER[1], "label": "인문사회캠퍼스 기준"}


def test_resolve_keeps_location_inside_service_area():
    inside = north_of(NATURAL_CENTER, 700)
    loc = campuses.resolve_search_location(location=inside, campus=NATURAL)
    assert loc == {"lat": inside["lat"], "lng": inside["lng"], "label": "현재 지도 중심"}
    # campus 를 주지 않으면 기본 캠퍼스(자연과학) 기준이다
    assert campuses.resolve_search_location(location=inside)["label"] == "현재 지도 중심"


def test_resolve_falls_back_when_location_is_outside():
    outside = north_of(NATURAL_CENTER, 1500)
    loc = campuses.resolve_search_location(location=outside, campus=NATURAL)
    assert loc == {"lat": NATURAL_CENTER[0], "lng": NATURAL_CENTER[1], "label": "자연과학캠퍼스 기준"}


def test_resolve_ignores_other_campus_area():
    # 인문사회 캠퍼스 안의 좌표라도 검색 대상이 자연과학이면 인정하지 않는다
    loc = campuses.resolve_search_location(
        location={"lat": HUMANITIES_CENTER[0], "lng": HUMANITIES_CENTER[1]}, campus=NATURAL)
    assert loc["label"] == "자연과학캠퍼스 기준" and loc["lat"] == NATURAL_CENTER[0]
    # 같은 좌표를 인문사회 기준으로 보면 인정한다
    loc = campuses.resolve_search_location(
        location={"lat": HUMANITIES_CENTER[0], "lng": HUMANITIES_CENTER[1]}, campus=HUMANITIES)
    assert loc["label"] == "현재 지도 중심"


@pytest.mark.parametrize("bad", [
    None, "37.29,126.97", [37.29, 126.97], {}, {"lat": 37.29}, {"lat": "37.29", "lng": "126.97"},
    {"lat": True, "lng": True}, {"lat": float("nan"), "lng": 126.97}, {"lat": 95, "lng": 126.97},
    {"lat": 37.29, "lng": 200},
])
def test_resolve_falls_back_when_location_is_malformed(bad):
    loc = campuses.resolve_search_location(location=bad, campus=NATURAL)
    assert loc == {"lat": NATURAL_CENTER[0], "lng": NATURAL_CENTER[1], "label": "자연과학캠퍼스 기준"}


@pytest.mark.parametrize("bad", ["없는캠퍼스", "", 1, ["자연과학"]])
def test_resolve_rejects_unknown_campus(bad):
    with pytest.raises(campuses.UnknownCampusError):
        campuses.resolve_search_location(campus=bad)


# --- 설정값 ----------------------------------------------------------------
def test_map_settings_are_consistent():
    assert map_settings.MAX_CANDIDATES == map_settings.PAGE_SIZE * map_settings.MAX_API_CALLS
    assert map_settings.PAGE_SIZE <= 15                       # 카카오 size 최대값
    assert len(map_settings.CATEGORY_CODES) == 18
    assert all(len(code) == 3 for code in map_settings.CATEGORY_CODES)
    assert map_settings.SEARCH_RADIUS_M <= 20_000             # 카카오 radius 최대값
