"""로그인 파트가 부르는 DB 함수 (db.user, db.profile, db.email_verification)와 seed.

마지막 테스트는 로그인 파트의 Flask 라우트(backend/api/auth)를 실제 DB에 붙여 한 바퀴 돌린다.
메일 발송만 가짜로 바꾼다.
"""
import base64
import os
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("DB_SECRET_KEY", base64.b64encode(b"k" * 32).decode())

from backend.db import configure, init_db, make_engine  # noqa: E402
from backend.db import email_verification as ev, profile, seed_data, user, users  # noqa: E402

BACKEND = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def seeded(tmp_path):
    engine = make_engine(str(tmp_path / "t.db"))
    init_db(engine)
    configure(engine)
    assert seed_data.load_reference() is True
    assert seed_data.load_reference() is False          # 두 번째는 건너뜀
    return engine


def test_seed_prototype(seeded):
    depts = profile.list_departments()
    assert len(depts) == 72 and {"id", "name"} == set(depts[0])
    assert profile.get_department_name(next(d["id"] for d in depts if d["name"] == "소프트웨어학과")) == "소프트웨어학과"
    assert [i["name"] for i in profile.list_interests()][:2] == ["장학", "취업"]


def test_user_create_and_lookup(seeded):
    u = user.create_user("Kim01@skku.edu")
    assert u == {"id": u["id"], "email": "kim01@skku.edu", "department_id": None}
    assert user.get_user_by_email("kim01@skku.edu") == u == user.get_user_by_id(u["id"])
    assert user.create_user("kim01@skku.edu") == u                 # 이미 있으면 그 사용자
    assert user.get_user_by_email("nobody@skku.edu") is None


def test_email_code_latest_row_wins(seeded):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ev.upsert_code("a@skku.edu", "h1", now + timedelta(minutes=10), now, 1, now)
    assert ev.increment_attempts("a@skku.edu") == 1
    ev.upsert_code("a@skku.edu", "h2", now + timedelta(minutes=10), now, 2, now)
    row = ev.get_code("a@skku.edu")
    assert (row["code_hash"], row["attempts"], row["send_count"]) == ("h2", 0, 2)   # 새 코드는 0부터
    assert row["expires_at"] == now + timedelta(minutes=10) and row["used_at"] is None
    ev.mark_code_used("a@skku.edu")
    assert ev.get_code("a@skku.edu")["used_at"] is not None
    assert ev.get_code("b@skku.edu") is None and ev.increment_attempts("b@skku.edu") == 0


def test_profile_and_interest_keywords(seeded):
    u = user.create_user("c@skku.edu")
    dept = profile.list_departments()[0]["id"]
    assert profile.interests_exist([1, 2]) and not profile.interests_exist([1, 999])
    row = profile.save_profile(u["id"], dept, [1, 2])
    assert row["department_id"] == dept and profile.list_user_interest_ids(u["id"]) == [1, 2]
    profile.save_profile(u["id"], dept, None)                       # None이면 관심사 그대로
    assert profile.list_user_interest_ids(u["id"]) == [1, 2]
    users.add_keyword(u["id"], "장학")                               # 관심사 '장학'과 겹침 -> 한 번만
    kws = users.list_keyword_subscribers()[0]["keywords"]
    assert sorted((k["keyword_norm"], k["source"]) for k in kws) == [("장학", "KEYWORD"), ("취업", "INTEREST")]
    profile.save_profile(u["id"], dept, [])
    assert profile.list_user_interest_ids(u["id"]) == []


def test_login_routes_end_to_end(tmp_path, monkeypatch):
    """로그인 파트 코드(api/auth)는 backend/를 import 기준으로 `db.*`를 부른다. 그 방식 그대로 붙인다."""
    flask = pytest.importorskip("flask")
    monkeypatch.syspath_prepend(str(BACKEND))
    monkeypatch.setenv("COOKIE_SECURE", "0")
    import db.engine as eng
    import db.seed_data as seed
    e = eng.make_engine(str(tmp_path / "api.db"))
    eng.init_db(e)
    eng.configure(e)
    seed.load_reference()

    import api
    import api.auth.routes as routes
    from api.auth.catalog import bp as catalog_bp
    from api.auth.me import bp as me_bp
    from api.errors import register_error_handlers
    sent = {}
    monkeypatch.setattr(routes, "send_verification_email", lambda email, code, ttl: sent.update(code=code))
    app = flask.Flask(__name__)
    app.config.update(SECRET_KEY="test-secret", TESTING=True)
    api._configure_session(app)
    register_error_handlers(app)
    for bp in (routes.bp, me_bp, catalog_bp):
        app.register_blueprint(bp)
    c = app.test_client()

    me = {"student_id": "kim01", "domain": 0}
    assert c.get("/api/me").get_json() == {"user": None, "needs_onboarding": False}
    r = c.post("/api/auth/email-code", json=me)
    assert r.status_code == 200 and r.get_json()["expires_in"] == 600
    assert c.post("/api/auth/email-code", json=me).status_code == 429          # 재발송 10초 대기
    wrong = "000000" if sent["code"] != "000000" else "111111"
    assert c.post("/api/auth/verify", json={**me, "code": wrong}).status_code == 400
    r = c.post("/api/auth/verify", json={**me, "code": sent["code"]})
    assert r.status_code == 200 and r.get_json()["needs_onboarding"] is True
    assert r.get_json()["user"]["email"] == "kim01@skku.edu"
    assert c.post("/api/auth/verify", json={**me, "code": sent["code"]}).status_code == 410   # 재사용 불가

    dept = next(d["id"] for d in c.get("/api/departments").get_json()["items"] if d["name"] == "소프트웨어학과")
    r = c.put("/api/me/profile", json={"department_id": dept, "interests": [1, 3]})
    assert r.status_code == 200 and r.get_json()["interests"] == [1, 3]
    assert c.get("/api/me").get_json()["needs_onboarding"] is False
    assert c.put("/api/me/profile", json={"department_id": 9999}).status_code == 422
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/me").get_json()["user"] is None
