"""대화 (채팅 API, 사이드바 이전 대화 목록, agent 문맥·기록) 초안.

테이블 session = 대화 하나 (로그인 세션 쿠키와는 별개. 로그인은 Flask 세션 쿠키, 이 id는 대화 id).
- 익명 대화는 user_id가 NULL. 로그인하면 claim_conversation으로 승계한다 (한 번 연결되면 다른 사용자로 못 바꿈).
- 소유 확인: user_id를 넘기면 그 사용자의 대화만, None이면 익명 대화만 접근 (익명 대화 id는 브라우저가 들고 있음).
- 메시지 role: 'user' | 'agent' | 'tool'. seq는 대화 안에서 1부터.
- 보존: 대화·tool·검색 기록 30일 (retention.py).
"""
import json
import uuid

from sqlalchemy import delete, func, select

from .engine import session_scope
from .models import Message, Retrieval, RetrievalHit, Session, ToolCall, UserMemory
from .util import now

TITLE_LEN = 30


def _conv(c: Session) -> dict:
    return {"id": c.session_id, "title": c.title, "created_at": c.created_at, "updated_at": c.updated_at}


def _owned(s, conversation_id: str, user_id: int | None) -> Session | None:
    c = s.get(Session, conversation_id)
    if c is None or c.expired_at is not None or c.user_id != user_id:
        return None
    return c


# ---------- 대화 ----------

def create_conversation(user_id: int | None = None, title: str | None = None) -> str:
    """새 대화 id (UUID). 익명이면 user_id None."""
    t = now()
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Session(session_id=cid, user_id=user_id, title=title, created_at=t, updated_at=t))
    return cid


def get_conversation(conversation_id: str, user_id: int | None) -> dict | None:
    """대화 정보 + 요약. 남의 대화거나 없으면 None (API는 404)."""
    with session_scope() as s:
        c = _owned(s, conversation_id, user_id)
        if c is None:
            return None
        return {**_conv(c), "summary": c.summary, "summary_upto_seq": c.summary_upto_seq}


def list_conversations(user_id: int, limit: int = 30, offset: int = 0) -> list[dict]:
    """사이드바 이전 대화 목록. 최근 대화 순."""
    with session_scope() as s:
        rows = s.scalars(select(Session).where(Session.user_id == user_id, Session.expired_at.is_(None))
                         .order_by(Session.updated_at.desc()).limit(limit).offset(offset))
        return [_conv(c) for c in rows]


def rename_conversation(conversation_id: str, user_id: int | None, title: str) -> bool:
    with session_scope() as s:
        c = _owned(s, conversation_id, user_id)
        if c is None:
            return False
        c.title = title[:100]
        return True


def delete_conversation(conversation_id: str, user_id: int | None) -> bool:
    """대화와 메시지·tool·검색 기록을 함께 지운다."""
    with session_scope() as s:
        c = _owned(s, conversation_id, user_id)
        if c is None:
            return False
        # ORM delete는 자식 FK를 NULL로 바꾸려 하므로 SQL DELETE로 DB의 CASCADE에 맡긴다
        s.execute(delete(Session).where(Session.session_id == conversation_id))
        return True


def claim_conversation(conversation_id: str, user_id: int) -> bool:
    """익명 대화를 로그인한 사용자에게 붙인다. 이미 그 사용자 것이면 True, 남의 것이면 False."""
    with session_scope() as s:
        c = s.get(Session, conversation_id)
        if c is None or (c.user_id is not None and c.user_id != user_id):
            return False
        c.user_id = user_id
        return True


# ---------- 메시지 ----------

def _msg(m: Message) -> dict:
    return {"id": m.message_id, "seq": m.seq, "role": m.role, "content": m.content, "model": m.model,
            "created_at": m.created_at}


def add_message(conversation_id: str, role: str, content: str, model: str | None = None) -> dict:
    """메시지 추가. 첫 user 메시지면 대화 제목을 그 앞부분으로 채운다. 반환 {id, seq, ...}."""
    t = now()
    with session_scope() as s:
        c = s.get(Session, conversation_id)
        if c is None:
            raise ValueError("없는 대화")
        seq = (s.scalar(select(func.max(Message.seq)).where(Message.session_id == conversation_id)) or 0) + 1
        m = Message(session_id=conversation_id, seq=seq, role=role, content=content, model=model, created_at=t)
        s.add(m)
        c.updated_at = t
        if c.title is None and role == "user":
            c.title = content.strip().replace("\n", " ")[:TITLE_LEN]
        s.flush()
        return _msg(m)


def list_messages(conversation_id: str, user_id: int | None, after_seq: int = 0,
                  limit: int | None = None) -> list[dict] | None:
    """대화 화면 복원, agent 문맥 구성. after_seq보다 뒤의 메시지, seq 순. 남의 대화면 None."""
    with session_scope() as s:
        if _owned(s, conversation_id, user_id) is None:
            return None
        q = (select(Message).where(Message.session_id == conversation_id, Message.seq > after_seq)
             .order_by(Message.seq))
        if limit:
            q = q.limit(limit)
        return [_msg(m) for m in s.scalars(q)]


def recall_conversation(conversation_id: str, query: str | None = None, last_n: int = 10) -> list[dict]:
    """agent tool용 원본 대화 조회 (요약으로 빠진 내용 확인). query가 있으면 그 말이 들어간 메시지만.

    소유 확인은 호출하는 쪽(서버가 주입한 대화 id)에서 끝났다고 본다.
    """
    q = select(Message).where(Message.session_id == conversation_id, Message.role != "tool")
    if query:
        q = q.where(Message.content.contains(query))
    with session_scope() as s:
        rows = s.scalars(q.order_by(Message.seq.desc()).limit(last_n)).all()
        return [_msg(m) for m in reversed(rows)]


def save_summary(conversation_id: str, summary: str, upto_seq: int) -> None:
    """앞부분 대화 요약 저장 (agent가 문맥이 길어지면)."""
    with session_scope() as s:
        c = s.get(Session, conversation_id)
        c.summary, c.summary_upto_seq = summary, upto_seq


# ---------- tool·검색 기록 ----------

def log_tool_call(message_id: int, tool_name: str, tool_input: dict, success: bool,
                  result_summary: str | None = None, duration_ms: int | None = None) -> int:
    """agent 메시지에 딸린 tool 호출 기록. 사용자 식별자 같은 서버 주입 값은 tool_input에서 빼고 넘길 것."""
    with session_scope() as s:
        c = ToolCall(message_id=message_id, tool_name=tool_name,
                     input_json=json.dumps(tool_input, ensure_ascii=False), success=int(success),
                     result_summary=result_summary, duration_ms=duration_ms, called_at=now())
        s.add(c)
        s.flush()
        return c.call_id


def log_retrieval(message_id: int, query: str, filters: dict, hits: list[dict], index_id: int | None = None) -> int:
    """검색 기록. hits: [{chunk_id, score, adopted?}] 순위 순. 결과 0건도 기록한다."""
    with session_scope() as s:
        r = Retrieval(message_id=message_id, query=query, filter_json=json.dumps(filters, ensure_ascii=False),
                      index_id=index_id, hit_count=len(hits), searched_at=now())
        s.add(r)
        s.flush()
        s.add_all([RetrievalHit(retrieval_id=r.retrieval_id, rank=i + 1, chunk_id=h["chunk_id"], score=h["score"],
                                adopted=int(bool(h.get("adopted")))) for i, h in enumerate(hits)])
        return r.retrieval_id


# ---------- 사용자 기억 (작업 환경) ----------

def _mem(m: UserMemory) -> dict:
    return {"id": m.memory_id, "content": m.content, "created_at": m.created_at, "updated_at": m.updated_at}


def list_memories(user_id: int) -> list[dict]:
    with session_scope() as s:
        return [_mem(m) for m in s.scalars(select(UserMemory).where(UserMemory.user_id == user_id)
                                           .order_by(UserMemory.updated_at.desc()))]


def add_memory(user_id: int, content: str, source_message_id: int | None = None) -> dict:
    t = now()
    with session_scope() as s:
        m = UserMemory(user_id=user_id, content=content, source_message_id=source_message_id,
                       created_at=t, updated_at=t)
        s.add(m)
        s.flush()
        return _mem(m)


def update_memory(user_id: int, memory_id: int, content: str) -> bool:
    with session_scope() as s:
        m = s.get(UserMemory, memory_id)
        if m is None or m.user_id != user_id:
            return False
        m.content, m.updated_at = content, now()
        return True


def delete_memory(user_id: int, memory_id: int) -> bool:
    with session_scope() as s:
        return s.execute(delete(UserMemory).where(UserMemory.memory_id == memory_id,
                                                  UserMemory.user_id == user_id)).rowcount > 0
