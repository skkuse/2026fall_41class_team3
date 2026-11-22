"""검색 대상 문서·청크와 Agent 검색 `search()` 초안.

- 원본(조문·별표·공지)은 각 테이블, 검색 단위는 document -> chunk. 청크 텍스트는 SQLite에만 둔다.
- Chroma(벡터 색인)에는 chunk_id·임베딩·필터 메타데이터만 넣는다. 색인 담당 코드가
  chunks_for_indexing()으로 가져가 넣고, pending_tombstones()로 지울 것을 가져간다.
- search(): vector_search 함수를 넘기면 벡터 검색, 없으면 SQLite 키워드 검색 (Chroma 없이도 돌려볼 수 있게).

청킹 규칙 'para-v1' (임시): 빈 줄 기준 문단을 MAX_CHARS 안에서 이어 붙인다.
"""
import re
from collections.abc import Callable

from sqlalchemy import delete, func, or_, select

from .engine import session_scope
from .models import Annex, Article, Chunk, ChunkTombstone, Document, IndexConfig, Notice
from .util import now

CHUNK_RULE = "para-v1"
MAX_CHARS = 800

# Chroma 메타데이터는 NULL을 못 받아 대체값을 쓴다 (10-26 확인)
META_NULL = {"dept_id": 0, "campus": "전체", "published_year": 9999}


# ---------- 청킹 ----------

def split_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > max_chars:                    # 너무 긴 문단은 자른다
            if cur:
                out.append(cur)
                cur = ""
            out.append(p[:max_chars])
            p = p[max_chars:]
        if cur and len(cur) + 2 + len(p) > max_chars:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def _source_text(s, d: Document) -> str:
    model = {"article": Article, "annex": Annex, "notice": Notice}[d.source_table]
    src = s.get(model, d.source_id)
    if src is None:
        return ""
    return src.body if d.source_table == "notice" else src.content


def _tombstone(s, chunk_ids: list[int], rule: str) -> None:
    t = now()
    for cid in chunk_ids:
        s.merge(ChunkTombstone(chunk_id=cid, chunk_rule=rule, deleted_at=t))


def rebuild_chunks(doc_id: int, rule: str = CHUNK_RULE) -> list[int]:
    """문서의 청크를 원본에서 다시 만든다 (공지 수정, 새 규정 버전 뒤). 이전 청크는 tombstone으로."""
    with session_scope() as s:
        d = s.get(Document, doc_id)
        old = list(s.scalars(select(Chunk.chunk_id).where(Chunk.doc_id == doc_id, Chunk.chunk_rule == rule)))
        if old:
            _tombstone(s, old, rule)
            s.execute(delete(Chunk).where(Chunk.chunk_id.in_(old)))
        t = now()
        new = [Chunk(doc_id=doc_id, seq=i + 1, text_=txt, token_count=len(txt.split()), chunk_rule=rule,
                     created_at=t) for i, txt in enumerate(split_text(_source_text(s, d)))]
        s.add_all(new)
        s.flush()
        return [c.chunk_id for c in new]


def docs_without_chunks(rule: str = CHUNK_RULE) -> list[int]:
    """아직 청크가 없는 문서 (새로 들어온 공지·조문)."""
    with session_scope() as s:
        return list(s.scalars(select(Document.doc_id).where(
            ~Document.doc_id.in_(select(Chunk.doc_id).where(Chunk.chunk_rule == rule))).order_by(Document.doc_id)))


def rebuild_pending(rule: str = CHUNK_RULE) -> int:
    """청크 없는 문서를 전부 청킹한다. 만든 청크 수."""
    return sum(len(rebuild_chunks(d, rule)) for d in docs_without_chunks(rule))


def invalidate_chunks(s, doc_id: int) -> None:
    """원본이 바뀐 문서의 청크를 지운다 (모든 규칙). 다음 rebuild_pending이 다시 만든다. 같은 트랜잭션 안에서."""
    old = s.execute(select(Chunk.chunk_id, Chunk.chunk_rule).where(Chunk.doc_id == doc_id)).all()
    for cid, rule in old:
        _tombstone(s, [cid], rule)
    if old:
        s.execute(delete(Chunk).where(Chunk.doc_id == doc_id))


def drop_documents(s, doc_ids: list[int], rule: str = CHUNK_RULE) -> None:
    """문서를 지운다 (청크는 CASCADE, 색인 삭제용 tombstone은 남김). 같은 트랜잭션 안에서 호출."""
    if not doc_ids:
        return
    _tombstone(s, list(s.scalars(select(Chunk.chunk_id).where(Chunk.doc_id.in_(doc_ids)))), rule)
    s.execute(delete(Document).where(Document.doc_id.in_(doc_ids)))


# ---------- 색인 동기화 (Chroma 담당 코드가 부름) ----------

def _meta(d: Document) -> dict:
    return {"doc_id": d.doc_id, "doc_type": d.doc_type, "trust_level": d.trust_level,
            "dept_id": d.dept_id if d.dept_id is not None else META_NULL["dept_id"],
            "campus": d.campus or META_NULL["campus"],
            "published_year": int(d.published_at[:4]) if d.published_at else META_NULL["published_year"]}


def chunks_for_indexing(rule: str = CHUNK_RULE, after_chunk_id: int = 0, limit: int = 500) -> list[dict]:
    """[{chunk_id, text, metadata}] chunk_id 순. 임베딩할 텍스트는 문서 제목 + 청크."""
    with session_scope() as s:
        rows = s.execute(select(Chunk, Document).join(Document, Chunk.doc_id == Document.doc_id)
                         .where(Chunk.chunk_rule == rule, Chunk.chunk_id > after_chunk_id)
                         .order_by(Chunk.chunk_id).limit(limit)).all()
        return [{"chunk_id": c.chunk_id, "text": f"{d.title}\n{c.text_}", "metadata": _meta(d)} for c, d in rows]


def pending_tombstones(rule: str = CHUNK_RULE) -> list[int]:
    with session_scope() as s:
        return list(s.scalars(select(ChunkTombstone.chunk_id).where(ChunkTombstone.chunk_rule == rule)))


def clear_tombstones(chunk_ids: list[int]) -> None:
    """색인에서 지운 뒤 호출."""
    with session_scope() as s:
        s.execute(delete(ChunkTombstone).where(ChunkTombstone.chunk_id.in_(chunk_ids)))


def create_index_config(name: str, embedding_model: str, dimension: int, chunk_rule: str = CHUNK_RULE,
                        scope: str = "조문,별표,공지사항") -> int:
    with session_scope() as s:
        c = IndexConfig(name=name, embedding_model=embedding_model, dimension=dimension, chunk_rule=chunk_rule,
                        scope=scope, created_at=now())
        s.add(c)
        s.flush()
        return c.index_id


def activate_index(index_id: int, chunk_count: int) -> None:
    """색인 구축이 끝나면 이것만 활성으로."""
    with session_scope() as s:
        for c in s.scalars(select(IndexConfig)):
            c.is_active = int(c.index_id == index_id)
        s.get(IndexConfig, index_id).chunk_count = chunk_count


def get_active_index() -> dict | None:
    with session_scope() as s:
        c = s.scalar(select(IndexConfig).where(IndexConfig.is_active == 1))
        return None if c is None else {"index_id": c.index_id, "name": c.name, "embedding_model": c.embedding_model,
                                       "dimension": c.dimension, "chunk_rule": c.chunk_rule}


# ---------- 검색 ----------

def _doc_filters(filters: dict) -> list:
    """filters: doc_type(str|list), trust_level(str|list), dept_id(그 학과 + 학과 무관 문서),
    campus, published_from, published_to ('YYYY-MM-DD')."""
    conds = []
    for key, col in (("doc_type", Document.doc_type), ("trust_level", Document.trust_level)):
        v = filters.get(key)
        if v:
            conds.append(col.in_([v] if isinstance(v, str) else v))
    if filters.get("dept_id") is not None:
        conds.append(or_(Document.dept_id == filters["dept_id"], Document.dept_id.is_(None)))
    if filters.get("campus"):
        conds.append(or_(Document.campus == filters["campus"], Document.campus.is_(None)))
    if filters.get("published_from"):
        conds.append(Document.published_at >= filters["published_from"])
    if filters.get("published_to"):
        conds.append(Document.published_at <= filters["published_to"] + "￿")
    return conds


def chroma_where(filters: dict) -> dict:
    """같은 filters를 Chroma where 절로 (벡터 검색 함수에 넘길 때)."""
    conds = []
    for key in ("doc_type", "trust_level"):
        v = filters.get(key)
        if v:
            conds.append({key: {"$in": [v] if isinstance(v, str) else list(v)}})
    if filters.get("dept_id") is not None:
        conds.append({"dept_id": {"$in": [filters["dept_id"], META_NULL["dept_id"]]}})
    if filters.get("campus"):
        conds.append({"campus": {"$in": [filters["campus"], META_NULL["campus"]]}})
    if not conds:
        return {}
    return conds[0] if len(conds) == 1 else {"$and": conds}


def _hit(c: Chunk, d: Document, score: float) -> dict:
    return {"chunk_id": c.chunk_id, "score": round(score, 4), "text": c.text_, "doc_id": d.doc_id,
            "doc_type": d.doc_type, "title": d.title, "source_url": d.source_url, "trust_level": d.trust_level,
            "published_at": d.published_at, "dept_id": d.dept_id}


def search(query: str, filters: dict | None = None, k: int = 5, rule: str = CHUNK_RULE,
           vector_search: Callable[[str, dict, int], list[tuple[int, float]]] | None = None) -> list[dict]:
    """Agent 검색. [{chunk_id, score, text, doc_id, doc_type, title, source_url, trust_level, published_at, dept_id}].

    vector_search(query, chroma_where, k) -> [(chunk_id, score)]를 넘기면 그 결과를 채워서 돌려준다
    (날짜 필터는 SQLite에서 한 번 더 거른다). 없으면 키워드 검색: 검색어를 띄어쓰기로 나눠
    제목·본문에 들어간 단어 비율로 점수를 매긴다.
    """
    filters = filters or {}
    conds = _doc_filters(filters)
    with session_scope() as s:
        if vector_search is not None:
            pairs = vector_search(query, chroma_where(filters), k * 2)
            ids = [cid for cid, _ in pairs]
            rows = {c.chunk_id: (c, d) for c, d in s.execute(
                select(Chunk, Document).join(Document, Chunk.doc_id == Document.doc_id)
                .where(Chunk.chunk_id.in_(ids), *conds)).all()}
            return [_hit(*rows[cid], score) for cid, score in pairs if cid in rows][:k]

        terms = [t for t in re.split(r"\s+", query.strip()) if t]
        if not terms:
            return []
        rows = s.execute(select(Chunk, Document).join(Document, Chunk.doc_id == Document.doc_id)
                         .where(Chunk.chunk_rule == rule, *conds,
                                or_(*[or_(Chunk.text_.contains(t), Document.title.contains(t)) for t in terms]))).all()
        scored = []
        for c, d in rows:
            hay = f"{d.title}\n{c.text_}"
            scored.append((sum(t in hay for t in terms) / len(terms), c, d))
        scored.sort(key=lambda x: (-x[0], x[1].chunk_id))
        return [_hit(c, d, sc) for sc, c, d in scored[:k]]


def get_chunks(chunk_ids: list[int]) -> list[dict]:
    """근거로 인용할 청크 (검색 기록의 chunk_id로 다시 볼 때). 재색인으로 지워진 것은 빠진다."""
    with session_scope() as s:
        rows = s.execute(select(Chunk, Document).join(Document, Chunk.doc_id == Document.doc_id)
                         .where(Chunk.chunk_id.in_(chunk_ids))).all()
        return [_hit(c, d, 0.0) for c, d in rows]


def count_chunks(rule: str = CHUNK_RULE) -> int:
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(Chunk).where(Chunk.chunk_rule == rule))
