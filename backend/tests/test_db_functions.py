"""다른 파트에 주는 DB 함수의 기본 동작."""
import base64
import os

import pytest
from sqlalchemy import delete

from backend.db import configure, init_db, make_engine, session_scope
from backend.db import likes, notices, notifications, users
from backend.db.models import AppUser, Board, Department, Faculty
from backend.db.util import email_hash, encrypt_email, now

os.environ.setdefault("DB_SECRET_KEY", base64.b64encode(b"k" * 32).decode())


@pytest.fixture(autouse=True)
def db(tmp_path):
    engine = make_engine(str(tmp_path / "t.db"))
    init_db(engine)
    configure(engine)
    t = now()
    with session_scope() as s:
        s.add(Faculty(faculty_id=1, name="소프트웨어융합대학"))
        s.add(Faculty(faculty_id=2, name="공과대학"))
        s.flush()
        s.add(Department(dept_id=1, faculty_id=1, name="소프트웨어학과", campus="자연과학"))
        s.add(Department(dept_id=2, faculty_id=2, name="기계공학부", campus="자연과학"))
        s.flush()
        s.add_all([Board(board_id=1, name="학교 공지", scope="SCHOOL", list_url="u", allowed_host="skku.edu", parser_type="p"),
                   Board(board_id=2, name="소융대 공지", scope="COLLEGE", faculty_id=1, list_url="u", allowed_host="skku.edu", parser_type="p"),
                   Board(board_id=3, name="소프트 학과 공지", scope="DEPT", dept_id=1, list_url="u", allowed_host="skku.edu", parser_type="p")])
        for uid, dept, mail in [(1, 1, "a@skku.edu"), (2, 2, "b@skku.edu")]:
            s.add(AppUser(user_id=uid, email_enc=encrypt_email(mail), email_hash=email_hash(mail), dept_id=dept,
                          verified_at=t, created_at=t, last_access_at=t))
    yield engine


def post(no, title="장학 신청 안내", h="h1"):
    return {"category": "장학", "title": title, "title_norm": title, "dup_key": "k-" + title, "body": "본문",
            "posted_at": "2026-11-14", "url": f"https://skku.edu/{no}", "attachments": [{"name": "a.pdf", "url": "x"}],
            "content_hash": h, "article_no": no}


def test_user_scope_and_departments():
    assert users.get_user_scope(1) == {"is_verified": True, "dept_id": 1, "dept_name": "소프트웨어학과",
                                       "faculty_id": 1, "college_name": "소프트웨어융합대학"}
    assert users.get_user_scope(99) is None
    depts = users.list_departments()
    assert {d["name"] for d in depts} == {"소프트웨어학과", "기계공학부"}
    assert [d["board_url"] for d in depts if d["dept_id"] == 1] == ["u"]


def test_keywords_and_subscribers():
    assert users.add_keyword(1, " 장학 ")["keyword_norm"] == "장학"
    assert users.add_keyword(1, "장학") is None                       # 중복
    users.set_keywords(2, ["인턴", "인턴 ", "교환학생"])
    assert {k["keyword"] for k in users.list_keywords(2)} == {"인턴", "교환학생"}
    users.set_user_boards(1, [3])
    subs = users.list_keyword_subscribers(board_id=3)
    assert [(u["user_id"], u["email"]) for u in subs] == [(1, "a@skku.edu")]
    assert {u["user_id"] for u in users.list_keyword_subscribers()} == {1, 2}


def test_likes():
    assert likes.insert_like(1, "123", "http://place.map.kakao.com/123", "자연과학", "맛집")
    assert not likes.insert_like(1, "123", "http://place.map.kakao.com/123", "자연과학", "새 메모")
    with pytest.raises(ValueError):
        likes.insert_like(1, "124", "http://place.map.kakao.com/999", "자연과학")
    likes.insert_like(2, "123", "https://place.map.kakao.com/123", "자연과학")
    assert likes.like_stats(["123", "555"], user_id=2) == {"123": {"count": 2, "liked_by_me": True},
                                                           "555": {"count": 0, "liked_by_me": False}}
    assert likes.list_likes_by_user(1)[0]["memo"] == "새 메모"
    assert likes.delete_like(1, "123") and not likes.delete_like(1, "123")


def test_notice_flow_and_visibility():
    run = notices.start_crawl_run(3, now())
    nid = notices.create_notice(post(100), 3, tags=[{"scope": "DEPT", "dept_id": 1}])
    notices.finish_crawl_run(run, "SUCCESS", {"new_count": 1}, last_article_no=100)
    assert notices.list_active_boards()[2]["last_article_no"] == 100
    assert notices.find_posting(3, 100)["notice_id"] == nid
    assert [c["notice_id"] for c in notices.find_duplicate_candidates("k-장학 신청 안내", "2026-11-20")] == [nid]

    # 같은 공지가 학교 게시판에도 올라옴 -> 노출 범위 확대
    r = notices.add_notice_posting(nid, post(7), 1, overwrite=False, new_tags=[{"scope": "SCHOOL"}])
    assert r["tags_changed"]
    assert len(notices.get_notice(nid)["postings"]) == 2

    only_dept = notices.create_notice(post(101, "학과 행사"), 3, tags=[{"scope": "DEPT", "dept_id": 1}])
    seen_by_1, _ = notices.list_visible_notices(1)
    seen_by_2, _ = notices.list_visible_notices(2)
    assert {n["notice_id"] for n in seen_by_1} == {nid, only_dept}
    assert {n["notice_id"] for n in seen_by_2} == {nid}
    assert notices.list_visible_notices(None)[1] == 1

    failed = notices.start_crawl_run(2, now())
    notices.finish_crawl_run(failed, "FAILED", error_message="timeout", last_article_no=999)
    b2 = [b for b in notices.list_active_boards() if b["board_id"] == 2][0]
    assert b2["consecutive_failures"] == 1 and b2["last_article_no"] == 0   # 실패하면 커서 그대로


def test_notifications_once_per_user():
    nid = notices.create_notice(post(100), 3, tags=[{"scope": "DEPT", "dept_id": 1}])
    a = notifications.create_pending_notification(1, "NOTICE", nid, ["장학"])
    assert notifications.create_pending_notification(1, "NOTICE", nid, ["장학"]) is None
    notifications.mark_notification_failed(a, "smtp 451", permanent=False)
    assert [r["notification_id"] for r in notifications.list_retryable_notifications()] == [a]
    notifications.mark_notification_sent(a)
    rows, total = notifications.list_user_notifications(1)
    assert total == 1 and rows[0]["title"] == "장학 신청 안내"


def test_user_delete_cascades():
    users.add_keyword(1, "장학")
    likes.insert_like(1, "1", "http://place.map.kakao.com/1", "자연과학")
    with session_scope() as s:
        s.execute(delete(AppUser).where(AppUser.user_id == 1))
    assert users.list_keywords(1) == [] and likes.count_user_likes(1) == 0
