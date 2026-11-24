"""카카오 로컬 API 호출. 키는 환경변수 KAKAO_REST_API_KEY"""

import os
import requests
from services import map_settings
import logging
logger = logging.getLogger(__name__)


BASE_URL = "https://dapi.kakao.com/v2/local/search"
TIMEOUT_SEC = 5
SEARCH_TYPES = ("keyword", "category")
SORTS = ("distance", "accuracy")
MAX_RADIUS_M = 20_000      # 카카오 radius 최대값
MAX_PAGE = 45              # 카카오 page 최대값


class KakaoApiError(RuntimeError):
    """카카오 API 호출 실패"""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _build_params(search_location, search_type, query_or_code, radius, page, size, sort) -> dict:
    """인자를 검사하고 카카오 요청 파라미터로 변환. 잘못되면 ValueError"""
    if not (isinstance(search_location, dict) and _is_number(search_location.get("lat"))
            and _is_number(search_location.get("lng"))):
        raise ValueError("search_location 은 {lat, lng} 여야 함")
    if search_type not in SEARCH_TYPES:
        raise ValueError(f"search_type 은 {SEARCH_TYPES} 중 하나")
    if not _is_int(radius) or not 0 <= radius <= MAX_RADIUS_M:
        raise ValueError(f"radius 는 0~{MAX_RADIUS_M} 정수")
    if not _is_int(page) or not 1 <= page <= MAX_PAGE:
        raise ValueError(f"page 는 1~{MAX_PAGE} 정수")
    if not _is_int(size) or not 1 <= size <= map_settings.PAGE_SIZE:
        raise ValueError(f"size 는 1~{map_settings.PAGE_SIZE} 정수")
    if sort not in SORTS:
        raise ValueError(f"sort 는 {SORTS} 중 하나")

    params = {"x": search_location["lng"], "y": search_location["lat"],
              "radius": radius, "page": page, "size": size, "sort": sort}
    if search_type == "keyword":
        if not isinstance(query_or_code, str) or not query_or_code.strip():
            raise ValueError("keyword 검색은 query 필요")
        params["query"] = query_or_code.strip()
    else:
        if query_or_code not in map_settings.CATEGORY_CODES:
            raise ValueError(f"알 수 없는 카테고리 코드: {query_or_code!r}")
        params["category_group_code"] = query_or_code
    return params


def _error_message(resp) -> str:
    try:
        return str(resp.json().get("message", ""))
    except (ValueError, AttributeError):
        return ""


def fetch_places_page(search_location, search_type, query_or_code, radius=map_settings.SEARCH_RADIUS_M,
                      page=1, size=map_settings.PAGE_SIZE, sort=map_settings.SEARCH_SORT) -> dict:
    """카카오 로컬 API 한 페이지 호출. {"documents": [...], "is_end": bool} 반환 (documents 는 응답 그대로)

    search_type: "keyword"(query_or_code 는 검색어) 또는 "category"(카테고리 그룹 코드)
    실패하면 KakaoApiError, 인자가 잘못되면 ValueError
    """
    params = _build_params(search_location, search_type, query_or_code, radius, page, size, sort)
    key = os.environ.get("KAKAO_REST_API_KEY")
    if not key:
        raise KakaoApiError("KAKAO_REST_API_KEY 가 설정되지 않음")

    try:
        resp = requests.get(f"{BASE_URL}/{search_type}.json", params=params,
                            headers={"Authorization": f"KakaoAK {key}"}, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        raise KakaoApiError(f"카카오 API 요청 실패: {type(e).__name__}") from e

    if resp.status_code != 200:
        raise KakaoApiError(f"카카오 API 오류 {resp.status_code}: {_error_message(resp)}")
    try:
        data = resp.json()
    except ValueError:
        raise KakaoApiError("카카오 API 응답이 JSON 이 아님") from None

    documents = data.get("documents") if isinstance(data, dict) else None
    if not isinstance(documents, list):
        raise KakaoApiError("카카오 API 응답 형식 오류")
    meta = data.get("meta")
    is_end = meta.get("is_end", True) if isinstance(meta, dict) else True
    return {"documents": documents, "is_end": bool(is_end)}


def collect_pages(search_location, search_type, query_or_code, radius=map_settings.SEARCH_RADIUS_M,
                  sort=map_settings.SEARCH_SORT, max_pages=map_settings.MAX_API_CALLS) -> list[dict]:
    """최대 max_pages 페이지를 모아 documents 목록 반환. 마지막 페이지(is_end)면 중간에 멈춤"""
    if not _is_int(max_pages) or max_pages < 1:
        raise ValueError("max_pages 는 1 이상의 정수")
    documents: list[dict] = []
    for page in range(1, max_pages + 1):
        try:
            result = fetch_places_page(search_location, search_type, query_or_code,
                                       radius=radius, page=page, size=map_settings.PAGE_SIZE, sort=sort)
        except KakaoApiError:
            if page == 1:
                raise
            logger.warning("카카오 %d페이지 호출 실패, 앞 페이지 결과만 사용", page, exc_info=True)
            break
        documents.extend(result["documents"])
        if result["is_end"]:
            break
    return documents