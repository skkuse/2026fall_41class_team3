"""게시판·수집 실행·공지 (공지·알림 파트 요청, 공유 Docs "공지사항 키워드 알림 구독" 탭 DB 호출 API 1~3절).

ParsedPost는 크롤러가 파싱한 글 하나를 dict로 넘긴 것:
    {category, title, title_norm, dup_key, body, posted_at, url, attachments: [{name, url}],
     content_hash, article_no}
Tag는 {"scope": "SCHOOL"|"COLLEGE"|"DEPT", "faculty_id": int|None, "dept_id": int|None}.
"""
import json

from sqlalchemy import func, or_, select

from .engine import session_scope
from .models import Board, CrawlRun, Department, Document, Notice, NoticePosting, NoticeTag
from .util import now, shift

# ---------- 게시판·실행 관리 ----------

def _board(b: Board) -> dict:
    return {c: getattr(b, c) for c in ("board_id", "name", "scope", "faculty_id", "dept_id", "list_url",
                                       "allowed_host", "parser_type", "is_active", "consecutive_failures",
                                       "last_success_at", "last_article_no")}


def list_active_boards() -> list[dict]:
    with session_scope() as s:
        return [_board(b) for b in s.scalars(select(Board).where(Board.is_active == 1).order_by(Board.board_id))]


def start_crawl_run(board_id: int, cycle_started_at: str) -> int:
    with session_scope() as s:
        run = CrawlRun(board_id=board_id, cycle_started_at=cycle_started_at, started_at=now(), status="RUNNING")
        s.add(run)
        s.flush()
        return run.run_id


def finish_crawl_run(run_id: int, status: str, counts: dict | None = None, error_message: str | None = None,
                     last_article_no: int | None = None) -> None:
    """실행을 끝낸다. 성공이면 게시판의 last_success_at·실패 횟수 0·last_article_no(주면)를 함께 갱신.

    커서를 같은 트랜잭션에서 올려, 실패한 실행이 커서를 앞당기는 일이 없게 한다.
    """
    counts = counts or {}
    with session_scope() as s:
        run = s.get(CrawlRun, run_id)
        run.status, run.finished_at, run.error_message = status, now(), error_message
        for k in ("fetched_count", "new_count", "updated_count", "skipped_count"):
            if k in counts:
                setattr(run, k, counts[k])
        board = s.get(Board, run.board_id)
        if status == "SUCCESS":
            board.last_success_at, board.consecutive_failures = run.finished_at, 0
            if last_article_no is not None and last_article_no > board.last_article_no:
                board.last_article_no = last_article_no
        elif status == "FAILED":
            board.consecutive_failures += 1


def set_board_active(board_id: int, is_active: bool) -> None:
    with session_scope() as s:
        s.get(Board, board_id).is_active = int(is_active)


def last_successful_sync_at(dept_id: int | None = None) -> str | None:
    """캘린더 API의 lastSuccessfulSyncAt. dept_id를 주면 그 학과 게시판 기준, 없으면 전체."""
    with session_scope() as s:
        q = select(func.max(Board.last_success_at))
        if dept_id is not None:
            q = q.where(Board.dept_id == dept_id)
        return s.scalar(q)


# ---------- 공지 저장 ----------

def _set_tags(s, notice: Notice, tags: list[dict]) -> bool:
    """없는 태그만 추가한다. 하나라도 늘었으면 True."""
    have = {(t.scope, t.faculty_id, t.dept_id) for t in notice.notice_tag}
    added = False
    for t in tags or []:
        key = (t["scope"], t.get("faculty_id"), t.get("dept_id"))
        if key not in have:
            notice.notice_tag.append(NoticeTag(scope=key[0], faculty_id=key[1], dept_id=key[2]))
            have.add(key)
            added = True
    return added


def _fill(notice: Notice, post: dict) -> None:
    notice.category, notice.title, notice.title_norm = post.get("category"), post["title"], post["title_norm"]
    notice.dup_key, notice.body, notice.posted_at, notice.url = post["dup_key"], post["body"], post["posted_at"], post["url"]
    notice.attachments_json = json.dumps(post.get("attachments") or [], ensure_ascii=False)
    notice.content_hash = post["content_hash"]


def _posting(post: dict, board_id: int, t: str) -> NoticePosting:
    return NoticePosting(board_id=board_id, article_no=post["article_no"], url=post["url"],
                         posted_at=post["posted_at"], content_hash=post["content_hash"],
                         first_seen_at=t, last_seen_at=t)


def _sync_document(s, notice: Notice) -> None:
    """검색 대상 문서를 공지와 맞춘다 (청크·임베딩은 색인 파이프라인이 doc 단위로 다시 만든다)."""
    doc = s.scalar(select(Document).where(Document.source_table == "notice", Document.source_id == notice.notice_id))
    if doc is None:
        doc = Document(doc_type="공지사항", source_table="notice", source_id=notice.notice_id,
                       trust_level="공식 공지", collected_at=notice.collected_at)
        s.add(doc)
    depts = [t.dept_id for t in notice.notice_tag if t.scope == "DEPT"]
    doc.title, doc.source_url, doc.published_at = notice.title, notice.url, notice.posted_at
    doc.dept_id = depts[0] if len(depts) == 1 else None


def find_posting(board_id: int, article_no: int) -> dict | None:
    with session_scope() as s:
        p = s.scalar(select(NoticePosting).where(NoticePosting.board_id == board_id,
                                                 NoticePosting.article_no == article_no))
        if p is None:
            return None
        return {"posting_id": p.posting_id, "notice_id": p.notice_id, "content_hash": p.content_hash,
                "url": p.url, "posted_at": p.posted_at}


def find_duplicate_candidates(dup_key: str, posted_at: str, window_days: int = 14) -> list[dict]:
    """같은 dup_key이고 게시일 차이가 window_days 이내인 공지. 본문 유사도 판정은 호출하는 쪽."""
    lo, hi = shift(posted_at, days=-window_days), shift(posted_at, days=window_days)
    with session_scope() as s:
        rows = s.scalars(select(Notice).where(Notice.dup_key == dup_key, Notice.posted_at >= lo[:10],
                                              Notice.posted_at <= hi)).all()
        return [_notice(n) for n in rows]


def create_notice(post: dict, board_id: int, tags: list[dict] | None = None) -> int:
    """새 공지 + 첫 게시 위치 + 노출 태그 + 검색 문서를 한 트랜잭션으로 만든다."""
    t = now()
    with session_scope() as s:
        n = Notice(collected_at=t, last_checked_at=t, content_updated_at=t, tags_changed_at=t)
        _fill(n, post)
        n.notice_posting.append(_posting(post, board_id, t))
        _set_tags(s, n, tags or [])
        s.add(n)
        s.flush()
        _sync_document(s, n)
        return n.notice_id


def add_notice_posting(notice_id: int, post: dict, board_id: int, overwrite: bool,
                       new_tags: list[dict] | None = None) -> dict:
    """이미 있는 공지가 다른 게시판에도 올라온 경우. overwrite면 내용을 새 글로 덮어쓴다."""
    t = now()
    with session_scope() as s:
        n = s.get(Notice, notice_id)
        p = _posting(post, board_id, t)
        n.notice_posting.append(p)
        if overwrite:
            _fill(n, post)
            n.content_updated_at = t
        changed = _set_tags(s, n, new_tags or [])
        if changed:
            n.tags_changed_at = t
        n.last_checked_at = t
        s.flush()
        _sync_document(s, n)
        return {"posting_id": p.posting_id, "tags_changed": changed}


def update_notice_content(notice_id: int, posting_id: int, post: dict) -> None:
    """원문이 수정됐을 때."""
    t = now()
    with session_scope() as s:
        n = s.get(Notice, notice_id)
        _fill(n, post)
        n.content_updated_at = n.last_checked_at = t
        p = s.get(NoticePosting, posting_id)
        p.content_hash, p.last_seen_at = post["content_hash"], t
        _sync_document(s, n)


def touch_posting(posting_id: int, seen_at: str | None = None) -> None:
    """변경 없음. 확인 시각만 남긴다."""
    t = seen_at or now()
    with session_scope() as s:
        p = s.get(NoticePosting, posting_id)
        p.last_seen_at = t
        s.get(Notice, p.notice_id).last_checked_at = t


def update_notice_summary(notice_id: int, deadline: str | None, target: str | None, method: str | None) -> None:
    with session_scope() as s:
        n = s.get(Notice, notice_id)
        n.summary_deadline, n.summary_target, n.summary_how = deadline, target, method


# ---------- 공지 조회 ----------

def _tag(t: NoticeTag) -> dict:
    name = "성균관대학교" if t.scope == "SCHOOL" else (t.faculty.name if t.scope == "COLLEGE" else t.dept.name)
    return {"scope": t.scope, "name": name, "faculty_id": t.faculty_id, "dept_id": t.dept_id}


def _notice(n: Notice, with_body: bool = True) -> dict:
    d = {"notice_id": n.notice_id, "category": n.category, "title": n.title, "posted_at": n.posted_at,
         "url": n.url, "attachments": json.loads(n.attachments_json or "[]"),
         "summary": {"deadline": n.summary_deadline, "target": n.summary_target, "method": n.summary_how},
         "tags": [_tag(t) for t in n.notice_tag], "content_updated_at": n.content_updated_at}
    if with_body:
        d["body"] = n.body
    return d


def get_notice(notice_id: int) -> dict | None:
    """공지 상세. 노출 태그와 실린 게시판 목록을 포함한다."""
    with session_scope() as s:
        n = s.get(Notice, notice_id)
        if n is None:
            return None
        d = _notice(n)
        d["postings"] = [{"board_id": p.board_id, "board_name": p.board.name, "url": p.url}
                         for p in n.notice_posting]
        return d


def get_notice_tags(notice_id: int) -> list[dict]:
    with session_scope() as s:
        n = s.get(Notice, notice_id)
        return [_tag(t) for t in n.notice_tag] if n else []


def _visible_to(dept_id: int | None):
    """dept_id 학과 사용자에게 보이는 공지 조건. None이면 학교 전체 공지만 (학과를 모르는 익명 사용자)."""
    conds = [NoticeTag.scope == "SCHOOL"]
    if dept_id is not None:
        conds.append(NoticeTag.dept_id == dept_id)
        conds.append((NoticeTag.scope == "COLLEGE") & (NoticeTag.faculty_id ==
                     select(Department.faculty_id).where(Department.dept_id == dept_id).scalar_subquery()))
    return Notice.notice_id.in_(select(NoticeTag.notice_id).where(or_(*conds)))


def list_visible_notices(dept_id: int | None = None, query: str | None = None, category: str | None = None,
                         posted_from: str | None = None, posted_to: str | None = None,
                         limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    """(공지 목록, 전체 개수). 게시일 내림차순. 본문은 빼고 준다."""
    conds = [_visible_to(dept_id)]
    if query:
        conds.append(or_(Notice.title.contains(query), Notice.body.contains(query)))
    if category:
        conds.append(Notice.category == category)
    if posted_from:
        conds.append(Notice.posted_at >= posted_from)
    if posted_to:
        conds.append(Notice.posted_at <= posted_to)
    with session_scope() as s:
        total = s.scalar(select(func.count()).select_from(Notice).where(*conds))
        rows = s.scalars(select(Notice).where(*conds).order_by(Notice.posted_at.desc(), Notice.notice_id.desc())
                         .limit(limit).offset(offset)).all()
        return [_notice(n, with_body=False) for n in rows], total


def list_notices_changed_since(since: str, field: str = "tags") -> list[dict]:
    """field="tags": 새 공지 + 노출 범위가 넓어진 공지 (알림 매칭용).
    field="content": 새 공지 + 내용이 바뀐 공지 (캘린더 일정 추출용)."""
    col = {"tags": Notice.tags_changed_at, "content": Notice.content_updated_at}[field]
    with session_scope() as s:
        return [_notice(n) for n in s.scalars(select(Notice).where(col > since).order_by(col))]
