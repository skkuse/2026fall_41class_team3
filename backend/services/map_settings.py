"""지도 기능의 상수. 값을 바꿀 때는 이 파일만 수정.

서비스 영역 반경은 config/campuses.json 에서 service_radius_m 으로 관리
"""

# --- 카카오 검색 ---------------------------------------------------------
SEARCH_RADIUS_M = 500        # 검색 결과 표시 반경 (기준 위치 중심)
SEARCH_SORT = "distance"     # 카카오 검색 정렬 기준
PAGE_SIZE = 15               # 카카오 한 페이지 문서 수 (카카오 최대값)
MAX_API_CALLS = 2            # 한 번의 검색에서 부르는 카카오 API 페이지 수
MAX_CANDIDATES = 30          # PAGE_SIZE * MAX_API_CALLS

# --- 결과 정리 -----------------------------------------------------------
DISPLAY_LIMIT = 15           # 화면에 보여 주는 최대 장소 수
LIKE_BOOST_LIMIT = 3         # 좋아요가 있는 장소를 상단에 올리는 최대 개수

# --- 좋아요 --------------------------------------------------------------
MEMO_MAX_LEN = 30            # 메모 최대 글자 수
LIKE_CAP_PER_USER = 100      # 사용자당 좋아요 최대 개수
LIKE_RATE_PER_MIN = 30       # 사용자당 분당 좋아요 요청(PUT, DELETE 합산) 최대 횟수
LIKE_RATE_WINDOW_SEC = 60    # 위 횟수를 세는 구간(초)
PLACE_URL_PREFIXES = (       # 허용하는 장소 URL. 뒤에 place_id 가 정확히 붙어야 한다 (DB의 CHECK와 같은 규칙)
    "http://place.map.kakao.com/",
    "https://place.map.kakao.com/",
)

# --- 카카오 카테고리 그룹 코드 (search_by_category 의 선택지) -----------------
CATEGORY_CODES = {
    "MT1": "대형마트",
    "CS2": "편의점",
    "PS3": "어린이집, 유치원",
    "SC4": "학교",
    "AC5": "학원",
    "PK6": "주차장",
    "OL7": "주유소, 충전소",
    "SW8": "지하철역",
    "BK9": "은행",
    "CT1": "문화시설",
    "AG2": "중개업소",
    "PO3": "공공기관",
    "AT4": "관광명소",
    "AD5": "숙박",
    "FD6": "음식점",
    "CE7": "카페",
    "HP8": "병원",
    "PM9": "약국",
}
