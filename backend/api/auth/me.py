"""사용자 개인 정보 엔드포인트: 로그인 상태 확인, 학과, 관심사 저장."""
from flask import Blueprint, g, jsonify, request

from api.errors import ApiError
from api.guards import auth_user_from_row, optional_user, require_user
from db.profile import (department_exists, interests_exist, list_user_interest_ids,
                        save_profile)

bp = Blueprint("me", __name__, url_prefix="/api")


def user_payload(user) -> dict:
    """응답에 나가는 user 객체. {id, email, department_id}를 모두 전송"""
    return {"id": user.id, "email": user.email, "department_id": user.department_id}


def needs_onboarding(user) -> bool:
    """학과가 비어 있는 경우에 필요한 온보딩(학과, 관심사 선택) 분기 기준"""
    return user.department_id is None


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_profile_input(body: dict) -> tuple[int, list[int] | None]:
    """(department_id, interest_ids)를 돌려준다. interest_ids가 None이면 '변경 없음'."""
    department_id = body.get("department_id")
    if not _is_int(department_id) or not department_exists(department_id):
        raise ApiError(422, "INVALID_REQUEST", "존재하지 않는 학과입니다.")

    interests = body.get("interests")
    if interests is None:
        return department_id, None
    if not isinstance(interests, list) or not all(_is_int(i) for i in interests):
        raise ApiError(422, "INVALID_REQUEST", "interests는 관심사 id 배열이어야 합니다.")
    interest_ids = list(dict.fromkeys(interests))          # 중복 제거, 순서 유지
    if not interests_exist(interest_ids):
        raise ApiError(422, "INVALID_REQUEST", "존재하지 않는 관심사가 있습니다.")
    return department_id, interest_ids


@bp.get("/me")
@optional_user
def get_me():
    """FE가 앱을 열 때 로그인 상태를 복원하는 데 쓴다. 비로그인도 오류가 아니라 200."""
    if g.user is None:
        return jsonify(user=None, needs_onboarding=False)
    return jsonify(user=user_payload(g.user), needs_onboarding=needs_onboarding(g.user))


@bp.put("/me/profile")
@require_user
def put_my_profile():
    """학과와 관심사를 저장한다. 온보딩과 이후 수정에 같이 사용."""
    body = request.get_json(silent=True) or {}
    department_id, interest_ids = validate_profile_input(body)

    # 한 트랜잭션에서 학과 저장 + 관심사 교체(interest_ids가 None이면 관심사는 그대로). 저장된 사용자 행을 돌려준다.
    user_row = save_profile(g.user.id, department_id, interest_ids)

    user = auth_user_from_row(user_row)
    return jsonify(user=user_payload(user), interests=list_user_interest_ids(user.id))
