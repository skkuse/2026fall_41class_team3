"""캠퍼스 정보와 검색 기준 위치 확정
"""

import copy
import json
import math
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "campuses.json"
EARTH_RADIUS_M = 6_371_000
CURRENT_MAP_CENTER_LABEL = "현재 지도 중심"


class UnknownCampusError(ValueError):
    """목록에 없는 캠퍼스 id."""


# --- 설정 파일 읽기 --------------------------------------------------------
def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_coordinate(lat, lng) -> bool:
    return _is_number(lat) and _is_number(lng) and -90 <= lat <= 90 and -180 <= lng <= 180


def load_campuses(path=CONFIG_PATH) -> dict[str, dict]:
    """campuses.json으로부터 {campus_id: 캠퍼스} 반환."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("campuses") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError('campuses.json의 "campuses" 값이 지정되지 않음')

    campuses: dict[str, dict] = {}
    for item in items:
        cid = item.get("id") if isinstance(item, dict) else None
        if not isinstance(cid, str) or not cid:
            raise ValueError(f"올바르지 않은 campus id: {item!r}")
        if cid in campuses:
            raise ValueError(f"중복 campus id: {cid}")
        if not isinstance(item.get("name"), str) or not item["name"]:
            raise ValueError(f"{cid}: name 필요")
        center = item.get("center")
        if not isinstance(center, dict) or not _is_coordinate(center.get("lat"), center.get("lng")):
            raise ValueError(f"{cid}: center 는 올바른 {{lat, lng}} 여야 한다")
        radius = item.get("service_radius_m")
        if not _is_number(radius) or radius <= 0:
            raise ValueError(f"{cid}: service_radius_m 은 0보다 큰 숫자여야 한다")
        if not isinstance(item.get("default"), bool):
            raise ValueError(f"{cid}: default 는 true 또는 false 여야 한다")
        campuses[cid] = item

    defaults = [cid for cid, c in campuses.items() if c["default"]]
    if len(defaults) != 1:
        raise ValueError(f"default 캠퍼스 개수 오류 ({len(defaults)}개)")
    return campuses


@lru_cache(maxsize=1)
def _campuses() -> dict[str, dict]:
    return load_campuses()


def _get(campus_id) -> dict:
    campus = _campuses().get(campus_id) if isinstance(campus_id, str) else None
    if campus is None:
        raise UnknownCampusError(f"알 수 없는 캠퍼스: {campus_id!r}")
    return campus


# --- 조회 ----------------------------------------------------------------
def is_valid_campus_id(campus_id) -> bool:
    """PUT 요청의 campus 값 검증과 resolve_search_location의 campus 검증"""
    return isinstance(campus_id, str) and campus_id in _campuses()


def get_campus_center(campus_id: str) -> dict:
    """지정된 캠퍼스에 대해 {lat, lng, name} 반환. 목록에 없으면 UnknownCampusError"""
    campus = _get(campus_id)
    return {"lat": campus["center"]["lat"], "lng": campus["center"]["lng"], "name": campus["name"]}


def get_default_campus() -> dict:
    """캠퍼스 기본값 반환 ({id, name, center, service_radius_m, default})"""
    for campus in _campuses().values():
        if campus["default"]:
            return copy.deepcopy(campus)
    raise RuntimeError("Unknown error")      # load_campuses에서 default 제한을 검사함


# --- 거리와 서비스 영역 -------------------------------------------------------
def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이의 거리 (미터, 구면 근사)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def is_within_service_area(lat, lng, campus_id: str) -> bool:
    """지정된 캠퍼스 중심에서 service_radius_m 이내 여부 검사.
    좌표 형식이 틀리면 False, 목록에 없는 캠퍼스면 UnknownCampusError."""
    campus = _get(campus_id)
    if not _is_coordinate(lat, lng):
        return False
    center = campus["center"]
    return distance_m(lat, lng, center["lat"], center["lng"]) <= campus["service_radius_m"]


# --- 검색 기준 위치 --------------------------------------------------------
def resolve_search_location(location=None, campus=None) -> dict:
    """검색 기준 위치 {lat, lng, label} 확정.

    1. 검색 대상 캠퍼스: campus, 없으면 기본 캠퍼스. 목록에 없는 id 면 UnknownCampusError
    2. location 이 그 캠퍼스 서비스 영역 안이면 location (label "현재 지도 중심")
    3. 없거나 영역 밖이거나 형식이 틀리면 거절하지 않고 그 캠퍼스 중심 (label "○○캠퍼스 기준")
    """
    campus_id = get_default_campus()["id"] if campus is None else campus
    info = _get(campus_id)

    if isinstance(location, dict):
        lat, lng = location.get("lat"), location.get("lng")
        if _is_coordinate(lat, lng) and is_within_service_area(lat, lng, campus_id):
            return {"lat": lat, "lng": lng, "label": CURRENT_MAP_CENTER_LABEL}

    center = info["center"]
    return {"lat": center["lat"], "lng": center["lng"], "label": f"{info['name']} 기준"}
