"""채팅 엔드포인트: 요청 값과 로그인 정보를 에이전트 context로 묶어 전달하고 결과를 응답에 담는다.

모델은 user_id·email을 보지 못한다. context는 도구가 runtime.context로만 읽는다.

임시 로직
"""
from flask import Blueprint, g, jsonify, request

from agent import run_agent                       # 팀 확정 필요: run_agent(message, context, system_prompt) -> (reply, artifacts)
from api.errors import ApiError
from api.guards import optional_user
from db.profile import get_department_name

bp = Blueprint("chat", __name__, url_prefix="/api")

MAX_MESSAGE_LEN = 1000                            # 임시 값, 팀과 확정 필요

BASE_PROMPT = "당신은 학교 커뮤니티 생활정보 도우미입니다."   # 실제 문구는 agent 담당과 합의


def build_system_prompt(user) -> str:
    """사용자 정보에 따라 시스템 프롬프트 변경. 세 경우: 비로그인 / 로그인, 학과 미설정 / 로그인, 학과 설정"""
    if user is None:
        return BASE_PROMPT + " 사용자는 로그인하지 않았습니다."
    if user.department_id is None:
        return BASE_PROMPT
    name = get_department_name(user.department_id)
    return BASE_PROMPT + (f" 사용자의 학과는 {name}입니다." if name else "")


def _optional_str(body: dict, key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(422, "INVALID_REQUEST", f"{key} 형식이 올바르지 않습니다.")
    return value


@bp.post("/chat")
@optional_user
def post_chat():
    body = request.get_json(silent=True) or {}

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ApiError(422, "INVALID_REQUEST", "메시지를 입력해 주세요.")
    message = message.strip()
    if len(message) > MAX_MESSAGE_LEN:
        raise ApiError(422, "INVALID_REQUEST", f"메시지는 {MAX_MESSAGE_LEN}자 이하여야 합니다.")

    campus = _optional_str(body, "campus")
    location = body.get("location")
    if location is not None and not (isinstance(location, dict)
                                     and all(isinstance(location.get(k), (int, float)) for k in ("lat", "lng"))):
        raise ApiError(422, "INVALID_REQUEST", "location은 {lat, lng}여야 합니다.")

    context = {
        "user_id": g.user.id if g.user else None,
        "department_id": g.user.department_id if g.user else None,
        "campus": campus,
        "location": location,
    }
    reply, artifacts = run_agent(message, context, build_system_prompt(g.user))
    return jsonify(reply=reply, artifacts=artifacts)