"""캘린더 파트 DB 함수 초안 (db.schedules)."""
import base64
import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("DB_SECRET_KEY", base64.b64encode(b"k" * 32).decode())

from backend.db import configure, init_db, make_engine, seed_data, user  # noqa: E402
from backend.db import schedules as sc  # noqa: E402


@pytest.fixture(autouse=True)
def db(tmp_path):
    engine = make_engine(str(tmp_path / "t.db"))
    init_db(engine)
    configure(engine)
    seed_data.load_reference()
    return engine


def ev(start, end=None, title=None, notice="100", **kw):
    return {"board_id": "cse", "notice_id": notice, "notice_title": "2026 SW 행사 안내", "source_url": "https://x",
            "start_at": start, "end_at": end, "event_title": title, "is_all_day": "T" not in start,
            "organizer": "소프트웨어학과", "summary": "요약", "location": None, **kw}


def test_faculties_grouped():
    fs = sc.get_all_faculties_with_departments()
    assert len(fs) == 17 and sum(len(f["departments"]) for f in fs) == 72
    assert set(fs[0]) == {"id", "name", "departments"}


def test_save_keep_and_link():
    r = sc.save_event_changes([ev("2026-11-20T14:00", "2026-11-21", "특강"), ev("2026-12-01")], 1)
    assert [x["action"] for x in r] == ["CREATE", "CREATE"]
    again = sc.save_event_changes([ev("2026-11-20T14:00", "2026-11-21", "특강")], [1, 2])   # 같은 일정, 다른 학과
    assert again == [{"action": "KEEP", "event_id": r[0]["event_id"]}]
    assert [e["title"] for e in sc.get_department_events(2)] == ["특강"]
    assert len(sc.find_events_by_notice("cse", 100)) == 2
    with pytest.raises(ValueError):
        sc.save_event_changes([ev("2026/11/20")], 1)


def test_month_window_and_calendar():
    sc.save_event_changes([ev("2026-08-31"), ev("2026-09-01"), ev("2027-01-31T10:00"), ev("2027-02-01"),
                           ev("2026-08-20", "2026-09-02", "걸친 일정")], 1)
    got = [e["start_at"] for e in sc.get_department_events(1, month="2026-11")]
    assert got == ["2026-08-20", "2026-09-01", "2027-01-31T10:00"]          # 9월~1월과 겹치는 것만
    cal = sc.get_department_calendar(1, "2026-11")
    assert cal["department_id"] == 1 and len(cal["events"]) == 3 and "last_successful_sync_at" in cal
    assert sc.get_department_calendar(9999) is None
    eid = cal["events"][0]["event_id"]
    assert sc.deactivate_event(eid) and len(sc.get_department_events(1, "2026-11")) == 2


def test_processing_result():
    assert sc.get_processing_result("cse", "7") is None
    sc.record_processing_result("cse", 7, "FAILED", error="schema")
    sc.record_processing_result("cse", 7, "COMPLETED", reason="행사", event_count=2)
    assert sc.get_processing_result("cse", "7")["status"] == "COMPLETED"


def test_google_tokens_and_export():
    u = user.create_user("g@skku.edu")["id"]
    eid = sc.save_event_changes([ev("2026-11-20")], 1)[0]["event_id"]
    assert sc.get_google_tokens(u) is None
    sc.save_google_tokens(u, "at1", datetime(2026, 11, 22, 12, tzinfo=timezone.utc), refresh_token="rt1")
    sc.save_google_tokens(u, "at2", "2026-11-22T13:00:00Z")                  # refresh 없음 -> 기존 유지
    t = sc.get_google_tokens(u)
    assert (t["access_token"], t["refresh_token"], t["expires_at"]) == ("at2", "rt1", "2026-11-22T13:00:00Z")
    assert sc.get_events_by_ids([eid, 999])[0]["event_id"] == eid
    sc.record_export(u, eid, "gid1")
    assert sc.get_exported_events(u, [eid]) == {eid: "gid1"}
    assert sc.delete_google_connection(u) and sc.get_google_tokens(u) is None
