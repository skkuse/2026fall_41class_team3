"""검색 평가 데이터 초안 (평가 질문 세트, 실행 결과). 규정 agent 평가용.

평가 실행 자체(검색 돌리고 hit@5·MRR 계산)는 hit_at_k / mrr 도우미로 하고 결과만 record_eval_run으로 남긴다.
"""
import json

from sqlalchemy import select

from .engine import session_scope
from .models import EvalQuestion, EvalRun, EvalSet
from .util import now


def create_eval_set(set_version: str, questions: list[dict], description: str | None = None) -> int:
    """questions: [{question, expected_evidence, expected_answer_type, author?}]. 넣은 질문 수."""
    with session_scope() as s:
        s.add(EvalSet(set_version=set_version, description=description, created_at=now()))
        s.add_all([EvalQuestion(set_version=set_version, question=q["question"],
                                expected_evidence=q["expected_evidence"],
                                expected_answer_type=q["expected_answer_type"], author=q.get("author"))
                   for q in questions])
    return len(questions)


def list_eval_questions(set_version: str) -> list[dict]:
    with session_scope() as s:
        return [{"id": q.question_id, "question": q.question, "expected_evidence": q.expected_evidence,
                 "expected_answer_type": q.expected_answer_type}
                for q in s.scalars(select(EvalQuestion).where(EvalQuestion.set_version == set_version)
                                   .order_by(EvalQuestion.question_id))]


def hit_at_k(ranked_titles: list[list[str]], expected: list[str], k: int = 5) -> float:
    """질문별 검색 결과 제목 목록과 기대 근거(예: '학칙 제25조')로 hit@k. 제목에 기대 근거가 들어 있으면 적중."""
    hits = [any(e in t for t in titles[:k]) for titles, e in zip(ranked_titles, expected)]
    return sum(hits) / len(hits) if hits else 0.0


def mrr(ranked_titles: list[list[str]], expected: list[str]) -> float:
    total = 0.0
    for titles, e in zip(ranked_titles, expected):
        total += next((1 / (i + 1) for i, t in enumerate(titles) if e in t), 0.0)
    return total / len(expected) if expected else 0.0


def record_eval_run(index_id: int, set_version: str, hit_at_5: float | None, mrr_value: float | None,
                    ragas: dict | None = None, failures: list | None = None) -> int:
    with session_scope() as s:
        r = EvalRun(run_at=now(), index_id=index_id, set_version=set_version, hit_at_5=hit_at_5, mrr=mrr_value,
                    ragas_json=json.dumps(ragas, ensure_ascii=False) if ragas else None,
                    failures_json=json.dumps(failures, ensure_ascii=False) if failures else None)
        s.add(r)
        s.flush()
        return r.run_id


def list_eval_runs(set_version: str | None = None) -> list[dict]:
    q = select(EvalRun).order_by(EvalRun.run_at.desc())
    if set_version:
        q = q.where(EvalRun.set_version == set_version)
    with session_scope() as s:
        return [{"run_id": r.run_id, "run_at": r.run_at, "index_id": r.index_id, "set_version": r.set_version,
                 "hit_at_5": r.hit_at_5, "mrr": r.mrr} for r in s.scalars(q)]
