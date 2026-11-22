"""대화, 규정, 검색, 보존 batch, 평가 (초안 모듈)."""
import base64
import os

import pytest
from sqlalchemy import update

os.environ.setdefault("DB_SECRET_KEY", base64.b64encode(b"k" * 32).decode())

from backend.db import configure, init_db, make_engine, session_scope, seed_data, user  # noqa: E402
from backend.db import conversations as cv, evaluation, notices, regulations as rg, retention, search  # noqa: E402
from backend.db.models import AppUser, Session  # noqa: E402
from backend.db.util import now, shift  # noqa: E402


@pytest.fixture(autouse=True)
def db(tmp_path):
    engine = make_engine(str(tmp_path / "t.db"))
    init_db(engine)
    configure(engine)
    seed_data.load_reference()
    return engine


def test_conversation_flow():
    u = user.create_user("a@skku.edu")["id"]
    anon = cv.create_conversation()
    m = cv.add_message(anon, "user", "휴학 신청은 언제까지 하나요?\n급해요")
    cv.add_message(anon, "agent", "학칙 제25조에 따르면 ...", model="gpt")
    assert m["seq"] == 1 and cv.get_conversation(anon, None)["title"] == "휴학 신청은 언제까지 하나요? 급해요"
    assert cv.list_messages(anon, u) is None                        # 아직 익명 대화
    assert cv.claim_conversation(anon, u) and not cv.claim_conversation(anon, 999)
    assert [x["role"] for x in cv.list_messages(anon, u)] == ["user", "agent"]
    assert cv.list_conversations(u)[0]["id"] == anon
    assert [x["seq"] for x in cv.recall_conversation(anon, query="학칙")] == [2]
    cv.save_summary(anon, "휴학 문의", 2)
    assert cv.get_conversation(anon, u)["summary_upto_seq"] == 2
    cv.log_tool_call(2, "search_regulation", {"query": "휴학"}, True, "3건", 120)
    cv.log_retrieval(2, "휴학", {"doc_type": "조문"}, [{"chunk_id": 1, "score": 0.9, "adopted": True}])
    mem = cv.add_memory(u, "기계공학부 3학년")
    assert cv.update_memory(u, mem["id"], "기계공학부 4학년") and cv.list_memories(u)[0]["content"] == "기계공학부 4학년"
    assert cv.delete_conversation(anon, u) and cv.list_conversations(u) == []


def test_regulation_versions_and_search():
    rid = rg.upsert_regulation("학칙", part="제1편")
    rg.add_regulation_version(rid, "일부개정", "2025-03-01", "https://law/1",
                              articles=[{"article_no": 25, "title": "휴학", "content": "휴학은 학기 개시 전까지 신청한다."}],
                              addenda=[{"content": "2020학번 이전은 종전 규정", "admission_year_to": 2020}])
    rg.add_regulation_version(rid, "일부개정", "2026-03-01", "https://law/2",
                              articles=[{"article_no": 25, "title": "휴학", "content": "휴학은 수업일수 1/4 전까지 신청한다."},
                                        {"article_no": 25, "branch_no": 2, "content": "군휴학은 언제든 가능하다."}])
    assert "1/4" in rg.get_article("학칙", 25)["content"]
    assert "개시 전" in rg.get_article("학칙", 25, on_date="2025-06-01")["content"]
    assert rg.get_article("학", 25, 2)["label"] == "학칙 제25조의2"
    assert rg.get_addenda("학칙", admission_year=2019, on_date="2025-06-01")[0]["admission_year_to"] == 2020
    with pytest.raises(ValueError):
        rg.add_regulation_version(rid, "일부개정", "2024-01-01", "x", articles=[])

    assert search.rebuild_pending() == 2                                     # 현행 조문 2개만 문서
    hits = search.search("휴학 신청", {"doc_type": "조문"})
    assert hits[0]["title"] == "학칙 제25조(휴학)" and hits[0]["score"] == 1.0
    assert search.chunks_for_indexing()[0]["metadata"]["dept_id"] == 0      # NULL 대체값
    fake = lambda q, where, k: [(hits[0]["chunk_id"], 0.77)]                # 벡터 검색 자리
    assert search.search("아무거나", {"doc_type": "조문"}, vector_search=fake)[0]["score"] == 0.77
    assert search.chroma_where({"doc_type": "조문", "dept_id": 3}) == {
        "$and": [{"doc_type": {"$in": ["조문"]}}, {"dept_id": {"$in": [3, 0]}}]}
    iid = search.create_index_config("reg-bge-m3", "BAAI/bge-m3", 1024)
    search.activate_index(iid, search.count_chunks())
    assert search.get_active_index()["index_id"] == iid


def test_notice_update_rechunks():
    post = {"category": "장학", "title": "장학 안내", "title_norm": "장학 안내", "dup_key": "k", "body": "첫 본문",
            "posted_at": "2026-11-14", "url": "https://skku.edu/1", "content_hash": "h1", "article_no": 1}
    nid = notices.create_notice(post, 1, tags=[{"scope": "SCHOOL"}])
    search.rebuild_pending()
    old = search.search("첫")[0]["chunk_id"]
    pid = notices.find_posting(1, 1)["posting_id"]
    notices.update_notice_content(nid, pid, {**post, "body": "바뀐 본문", "content_hash": "h2"})
    assert old in search.pending_tombstones() and search.search("첫") == []
    search.rebuild_pending()
    assert search.search("바뀐")[0]["doc_type"] == "공지사항"
    search.clear_tombstones([old])
    assert search.pending_tombstones() == []


def test_retention():
    u = user.create_user("old@skku.edu")["id"]
    keep = cv.create_conversation(u)
    gone = cv.create_conversation(u)
    anon = cv.create_conversation()
    old = shift(now(), days=-40)
    with session_scope() as s:
        s.execute(update(Session).where(Session.session_id.in_([gone])).values(updated_at=old))
        s.execute(update(Session).where(Session.session_id == anon).values(updated_at=shift(now(), days=-2)))
        s.execute(update(AppUser).where(AppUser.user_id == u).values(last_access_at=shift(now(), days=-400)))
    assert retention.purge_conversations() == 2 and cv.get_conversation(keep, u) is not None
    assert [x["id"] for x in retention.users_to_warn()] == [u]
    retention.mark_warned([u])
    assert retention.users_to_warn() == [] and retention.delete_warned_users() == 0   # 30일 유예
    with session_scope() as s:
        s.execute(update(AppUser).where(AppUser.user_id == u).values(deletion_notified_at=shift(now(), days=-31)))
    assert retention.delete_warned_users() == 1 and user.get_user_by_id(u) is None


def test_evaluation():
    evaluation.create_eval_set("v1", [{"question": "휴학 기한?", "expected_evidence": "학칙 제25조",
                                       "expected_answer_type": "단순 조회"}])
    assert evaluation.list_eval_questions("v1")[0]["expected_evidence"] == "학칙 제25조"
    ranked = [["학칙 제24조", "학칙 제25조(휴학)"]]
    assert evaluation.hit_at_k(ranked, ["학칙 제25조"]) == 1.0 and evaluation.mrr(ranked, ["학칙 제25조"]) == 0.5
    iid = search.create_index_config("i", "m", 8)
    rid = evaluation.record_eval_run(iid, "v1", 1.0, 0.5)
    assert evaluation.list_eval_runs("v1")[0]["run_id"] == rid
