"""선택지 목록 엔드포인트. 로그인 전에도 쓸 수 있어 데코레이터가 없다."""
from flask import Blueprint, jsonify

from db.profile import list_departments, list_interests

bp = Blueprint("catalog", __name__, url_prefix="/api")


@bp.get("/departments")
def get_departments():
    return jsonify(items=[{"id": d["id"], "name": d["name"]} for d in list_departments()])


@bp.get("/interests")
def get_interests():
    return jsonify(items=[{"id": i["id"], "name": i["name"]} for i in list_interests()])
