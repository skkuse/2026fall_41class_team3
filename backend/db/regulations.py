"""규정(학칙 등) 저장·조회 초안. 구조는 법제처 국가법령정보 형식: 규정 -> 버전 -> 조문·부칙·별표.

- 새 버전을 넣으면 이전 현행 버전의 effective_to를 닫고, 검색 문서는 새 버전 것으로 바꾼다
  (예전 버전 원문은 남아 있어 날짜를 주면 그때 조문을 볼 수 있다).
- 조문 번호: 제25조 -> article_no 25, 제25조의2 -> branch_no 2.
- 조회 결과의 source_url은 그 버전 원문 링크 (답변 출처 표시용).
"""
from datetime import date

from sqlalchemy import or_, select

from .engine import session_scope
from .models import Addendum, Annex, Article, Document, Regulation, RegulationVersion
from .search import drop_documents
from .util import now


def upsert_regulation(name: str, part: str | None = None, department_in_charge: str | None = None) -> int:
    with session_scope() as s:
        r = s.scalar(select(Regulation).where(Regulation.name == name))
        if r is None:
            r = Regulation(name=name)
            s.add(r)
        r.part, r.department_in_charge = part, department_in_charge
        s.flush()
        return r.reg_id


def _article_title(reg: str, a: Article) -> str:
    no = f"제{a.article_no}조" + (f"의{a.branch_no}" if a.branch_no else "")
    return f"{reg} {no}" + (f"({a.title})" if a.title else "")


def add_regulation_version(reg_id: int, amend_type: str, effective_from: str, source_url: str,
                           articles: list[dict], addenda: list[dict] | None = None,
                           annexes: list[dict] | None = None, promulgated_on: str | None = None,
                           amend_reason: str | None = None) -> int:
    """버전 하나를 조문·부칙·별표와 함께 한 트랜잭션으로 넣는다. version_id를 돌려준다.

    articles: [{article_no, branch_no?, title?, chapter?, content, effective_from?, is_changed?, source_page?}]
    addenda:  [{content, admission_year_from?, admission_year_to?}]
    annexes:  [{annex_no, branch_no?, title?, content}]
    """
    t = now()
    with session_scope() as s:
        reg = s.get(Regulation, reg_id)
        prev = s.scalar(select(RegulationVersion).where(RegulationVersion.reg_id == reg_id,
                                                        RegulationVersion.effective_to.is_(None)))
        if prev is not None and prev.effective_from >= effective_from:
            raise ValueError("버전은 시행일 순서대로 넣는다 (현행보다 늦은 시행일이어야 함)")
        if prev is not None:
            prev.effective_to = effective_from
            old_docs = list(s.scalars(select(Document.doc_id).where(or_(
                (Document.source_table == "article") & Document.source_id.in_(
                    select(Article.article_id).where(Article.version_id == prev.version_id)),
                (Document.source_table == "annex") & Document.source_id.in_(
                    select(Annex.annex_id).where(Annex.version_id == prev.version_id))))))
            drop_documents(s, old_docs)
        v = RegulationVersion(reg_id=reg_id, amend_type=amend_type, effective_from=effective_from,
                              source_url=source_url, promulgated_on=promulgated_on, amend_reason=amend_reason,
                              collected_at=t)
        s.add(v)
        s.flush()
        arts = [Article(version_id=v.version_id, article_no=a["article_no"], branch_no=a.get("branch_no", 0),
                        title=a.get("title"), chapter=a.get("chapter"), content=a["content"],
                        effective_from=a.get("effective_from"), is_changed=int(bool(a.get("is_changed"))),
                        source_page=a.get("source_page")) for a in articles]
        anns = [Annex(version_id=v.version_id, annex_no=x["annex_no"], branch_no=x.get("branch_no", 0),
                      title=x.get("title"), content=x["content"]) for x in annexes or []]
        s.add_all(arts + anns)
        s.add_all([Addendum(version_id=v.version_id, content=x["content"],
                            admission_year_from=x.get("admission_year_from"),
                            admission_year_to=x.get("admission_year_to")) for x in addenda or []])
        s.flush()
        # 새 버전이 현행이므로 그 조문·별표를 검색 문서로
        for a in arts:
            s.add(Document(doc_type="조문", source_table="article", source_id=a.article_id,
                           title=_article_title(reg.name, a), source_url=source_url,
                           published_at=a.effective_from or effective_from, collected_at=t,
                           trust_level="공식 규정"))
        for x in anns:
            s.add(Document(doc_type="별표", source_table="annex", source_id=x.annex_id,
                           title=f"{reg.name} 별표 {x.annex_no}" + (f"({x.title})" if x.title else ""),
                           source_url=source_url, published_at=effective_from, collected_at=t,
                           trust_level="공식 규정"))
        return v.version_id


def list_regulations() -> list[dict]:
    """규정 목록과 현행 버전 시행일."""
    with session_scope() as s:
        rows = s.execute(select(Regulation, RegulationVersion.effective_from)
                         .outerjoin(RegulationVersion, (RegulationVersion.reg_id == Regulation.reg_id)
                                    & RegulationVersion.effective_to.is_(None))
                         .order_by(Regulation.name)).all()
        return [{"id": r.reg_id, "name": r.name, "part": r.part, "department_in_charge": r.department_in_charge,
                 "effective_from": eff} for r, eff in rows]


def _version_at(s, regulation_name: str, on_date: str | None):
    """그 날짜에 시행 중인 버전. 이름은 정확히 같은 것 먼저, 없으면 포함하는 것."""
    d = on_date or date.today().isoformat()
    reg = s.scalar(select(Regulation).where(Regulation.name == regulation_name)) or \
        s.scalar(select(Regulation).where(Regulation.name.contains(regulation_name)).order_by(Regulation.name))
    if reg is None:
        return None, None
    v = s.scalar(select(RegulationVersion).where(
        RegulationVersion.reg_id == reg.reg_id, RegulationVersion.effective_from <= d,
        or_(RegulationVersion.effective_to.is_(None), RegulationVersion.effective_to > d))
        .order_by(RegulationVersion.effective_from.desc()))
    return reg, v


def get_article(regulation_name: str, article_no: int, branch_no: int = 0, on_date: str | None = None) -> dict | None:
    """조문 번호로 조회 (예: '학칙', 25). on_date('YYYY-MM-DD')를 주면 그날 시행 중이던 조문."""
    with session_scope() as s:
        reg, v = _version_at(s, regulation_name, on_date)
        if v is None:
            return None
        a = s.scalar(select(Article).where(Article.version_id == v.version_id, Article.article_no == article_no,
                                           Article.branch_no == branch_no))
        if a is None:
            return None
        return {"regulation": reg.name, "article_no": a.article_no, "branch_no": a.branch_no, "title": a.title,
                "chapter": a.chapter, "content": a.content, "effective_from": a.effective_from or v.effective_from,
                "source_url": v.source_url, "label": _article_title(reg.name, a)}


def get_annex(regulation_name: str, annex_no: int, branch_no: int = 0, on_date: str | None = None) -> dict | None:
    with session_scope() as s:
        reg, v = _version_at(s, regulation_name, on_date)
        if v is None:
            return None
        x = s.scalar(select(Annex).where(Annex.version_id == v.version_id, Annex.annex_no == annex_no,
                                         Annex.branch_no == branch_no))
        return None if x is None else {"regulation": reg.name, "annex_no": x.annex_no, "title": x.title,
                                       "content": x.content, "source_url": v.source_url}


def get_addenda(regulation_name: str, admission_year: int | None = None, on_date: str | None = None) -> list[dict]:
    """부칙. admission_year를 주면 그 입학년도에 적용되는 경과 규정만."""
    with session_scope() as s:
        reg, v = _version_at(s, regulation_name, on_date)
        if v is None:
            return []
        q = select(Addendum).where(Addendum.version_id == v.version_id)
        if admission_year is not None:
            q = q.where(or_(Addendum.admission_year_from.is_(None), Addendum.admission_year_from <= admission_year),
                        or_(Addendum.admission_year_to.is_(None), Addendum.admission_year_to >= admission_year))
        return [{"content": x.content, "admission_year_from": x.admission_year_from,
                 "admission_year_to": x.admission_year_to} for x in s.scalars(q)]
