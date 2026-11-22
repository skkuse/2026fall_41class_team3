"""캘린더 파트 DB 함수 초안 (공유 Docs '캘린더 api 및 tool 정리(정우진)' 2.5·3.7절, 6.1·6.2절 기준).

캘린더 파트가 보고 바로 쓰거나 피드백 주면 고친다. 함수 이름은 명세서 이름을 따랐다.

일정 시각 형식 (제안): 학교 일정이라 **한국 시간(KST) 그대로** 저장한다. 다른 테이블의 UTC 규칙과 다르다.
    종일 일정  'YYYY-MM-DD'          시간 있는 일정  'YYYY-MM-DDTHH:MM'
    end_at은 그 순간을 포함하지 않는다 (명세 4.5.2: 종료 시각을 모르면 다음 날 00:00).
이 형식이면 문자열 비교로 월 범위를 거를 수 있다.
"""
import re
from datetime import date, datetime

from sqlalchemy import delete, func, insert, select

from .engine import session_scope
from .models import (CalendarExport, Department, Faculty, GoogleConnection, Schedule, ScheduleProcessing,
                     t_schedule_department)
from .notices import last_successful_sync_at
from .util import decrypt_text, encrypt_text, from_dt, now

_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?")
DEFAULT_KIND = "학과 행사"


# ---------- 조회 (명세 2.5, 6.1) ----------

def get_all_faculties_with_departments() -> list[dict]:
    """GET /api/departments 용. [{id, name, departments: [{id, name}]}], 학부 id 순."""
    with session_scope() as s:
        rows = s.execute(select(Faculty.faculty_id, Faculty.name, Department.dept_id, Department.name)
                         .outerjoin(Department, Department.faculty_id == Faculty.faculty_id)
                         .order_by(Faculty.faculty_id, Department.dept_id)).all()
    out: dict[int, dict] = {}
    for fid, fname, did, dname in rows:
        f = out.setdefault(fid, {"id": fid, "name": fname, "departments": []})
        if did is not None:
            f["departments"].append({"id": did, "name": dname})
    return list(out.values())


def _event(e: Schedule) -> dict:
    """명세 6.1 events 항목과 같은 이름(snake_case). camelCase 변환은 API 쪽에서."""
    return {"event_id": e.schedule_id,
            "image_urls": [e.image_path] if e.image_path else [],   # 경로 -> URL 변환은 API 쪽
            "title": e.event_title or e.notice_title,
            "start_at": e.start_at, "end_at": e.end_at, "is_all_day": bool(e.all_day),
            "location": e.place, "organization": e.organizer, "summary": e.description,
            "source_url": e.source_url,
            "created_at": None, "updated_at": None,                   # 11/18 요청으로 열 삭제 -> 필요하면 다시 추가
            "notice_title": e.notice_title, "kind": e.kind, "target_audience": e.target_audience}


def _month_window(month: str, around: int) -> tuple[str, str]:
    """'2026-11', around=2 -> ('2026-09-01', '2027-02-01'). 끝은 포함하지 않음."""
    y, m = map(int, month.split("-"))
    def add(k):
        t = y * 12 + (m - 1) + k
        return date(t // 12, t % 12 + 1, 1).isoformat()
    return add(-around), add(around + 1)


def get_department_events(department_id: int, month: str | None = None, months_around: int = 2) -> list[dict]:
    """학과에 연결된 활성 일정, 시작 시각 순.

    month('YYYY-MM')를 주면 그 달 앞뒤 months_around개월과 기간이 겹치는 일정만 (명세 6.1).
    없으면 전체 (명세 1.3).
    """
    q = (select(Schedule).join(t_schedule_department, t_schedule_department.c.schedule_id == Schedule.schedule_id)
         .where(t_schedule_department.c.dept_id == department_id, Schedule.is_active == 1))
    if month:
        lo, hi = _month_window(month, months_around)
        q = q.where(Schedule.start_at < hi, func.coalesce(Schedule.end_at, Schedule.start_at) >= lo)
    with session_scope() as s:
        return [_event(e) for e in s.scalars(q.order_by(Schedule.start_at, Schedule.schedule_id))]


def get_department_calendar(department_id: int, month: str | None = None) -> dict | None:
    """GET /api/departments/{id}/events 응답 한 벌. 없는 학과면 None (API는 404)."""
    with session_scope() as s:
        d = s.get(Department, department_id)
        if d is None:
            return None
        name = d.name
    return {"department_id": department_id, "department_name": name,
            "events": get_department_events(department_id, month),
            "last_successful_sync_at": last_successful_sync_at(department_id)}


def get_events_by_ids(event_ids: list[int]) -> list[dict]:
    """Google 캘린더 등록할 일정 (명세 1.5). 없는 id는 빠진다."""
    with session_scope() as s:
        return [_event(e) for e in s.scalars(select(Schedule).where(Schedule.schedule_id.in_(set(event_ids))))]


# ---------- 저장 (명세 3.7) ----------

def find_events_by_notice(board_id: str, notice_id: str) -> list[dict]:
    """같은 공지에서 이미 뽑은 일정 (기존 일정 비교용)."""
    with session_scope() as s:
        return [_event(e) for e in s.scalars(select(Schedule).where(
            Schedule.board_id == str(board_id), Schedule.notice_id == str(notice_id)))]


def _check_time(v: str | None, field: str) -> None:
    if v is not None and not _TIME_RE.fullmatch(v):
        raise ValueError(f"{field} 형식은 'YYYY-MM-DD' 또는 'YYYY-MM-DDTHH:MM' (받은 값: {v!r})")


def save_event_changes(events: list[dict], department_id: int | list[int]) -> list[dict]:
    """검증된 일정을 저장하고 학과에 연결한다. 한 트랜잭션, 실패하면 전부 롤백.

    events 항목 (LLM 출력 + 크롤러 원본을 합친 것, 명세 4.4.3):
        board_id, notice_id, notice_title, source_url        크롤러 원본 (필수: notice_title)
        start_at(필수), end_at, is_all_day, organizer, summary, location, event_title
        kind ('학사일정'|'학과 행사'|'공지 마감', 없으면 '학과 행사'), image_path, target_audience
    같은 공지·같은 시작/종료·같은 제목의 일정이 이미 있으면 KEEP (학과 연결만 추가).
    반환: [{"action": "CREATE"|"KEEP", "event_id": int}] (입력 순서)
    """
    dept_ids = [department_id] if isinstance(department_id, int) else list(department_id)
    out = []
    with session_scope() as s:
        for ev in events:
            _check_time(ev["start_at"], "start_at")
            _check_time(ev.get("end_at"), "end_at")
            board, notice = (None if ev.get(k) is None else str(ev[k]) for k in ("board_id", "notice_id"))
            same = s.scalar(select(Schedule).where(
                Schedule.board_id.is_(board) if board is None else Schedule.board_id == board,
                Schedule.notice_id.is_(notice) if notice is None else Schedule.notice_id == notice,
                Schedule.start_at == ev["start_at"],
                Schedule.end_at.is_(None) if ev.get("end_at") is None else Schedule.end_at == ev["end_at"],
                func.coalesce(Schedule.event_title, "") == (ev.get("event_title") or "")))
            if same is not None:
                e, action = same, "KEEP"
            else:
                e = Schedule(notice_title=ev["notice_title"], event_title=ev.get("event_title"),
                             description=ev.get("summary"), start_at=ev["start_at"], end_at=ev.get("end_at"),
                             all_day=int(bool(ev.get("is_all_day"))), place=ev.get("location"),
                             organizer=ev.get("organizer"), target_audience=ev.get("target_audience"),
                             kind=ev.get("kind") or DEFAULT_KIND, source_url=ev.get("source_url"),
                             image_path=ev.get("image_path"), board_id=board, notice_id=notice)
                s.add(e)
                s.flush()
                action = "CREATE"
            linked = set(s.scalars(select(t_schedule_department.c.dept_id)
                                   .where(t_schedule_department.c.schedule_id == e.schedule_id)))
            new = [d for d in dict.fromkeys(dept_ids) if d not in linked]
            if new:
                s.execute(insert(t_schedule_department), [{"schedule_id": e.schedule_id, "dept_id": d} for d in new])
            out.append({"action": action, "event_id": e.schedule_id})
    return out


def deactivate_event(event_id: int) -> bool:
    """일정 취소 (추후 확장 DEACTIVATE). 조회에서 빠진다."""
    with session_scope() as s:
        e = s.get(Schedule, event_id)
        if e is None:
            return False
        e.is_active = 0
        return True


# ---------- 처리 결과 (명세 3.2.7) ----------

def record_processing_result(board_id: str, notice_id: str, status: str, reason: str | None = None,
                             error: str | None = None, event_count: int = 0) -> None:
    """status: COMPLETED | EXCLUDED | FAILED. 같은 공지는 마지막 결과로 덮어쓴다."""
    with session_scope() as s:
        key = (str(board_id), str(notice_id))
        r = s.get(ScheduleProcessing, key)
        if r is None:
            r = ScheduleProcessing(board_id=key[0], notice_id=key[1])
            s.add(r)
        r.status, r.reason, r.error, r.event_count, r.processed_at = status, reason, error, event_count, now()


def get_processing_result(board_id: str, notice_id: str) -> dict | None:
    """이미 처리한 공지인지 (같은 공지가 두 번 전달됐을 때 건너뛰기용)."""
    with session_scope() as s:
        r = s.get(ScheduleProcessing, (str(board_id), str(notice_id)))
        return None if r is None else {"status": r.status, "reason": r.reason, "error": r.error,
                                       "event_count": r.event_count, "processed_at": r.processed_at}


# ---------- Google 캘린더 연결 (명세 1.5·1.6, 6.2) ----------
# OAuth state와 보류 중인 등록 대상(eventId 목록)은 DB가 아니라 Flask 세션에 두는 것을 제안한다.

def save_google_tokens(user_id: int, access_token: str, expires_at: datetime | str,
                       refresh_token: str | None = None, google_account_id: str | None = None,
                       google_email: str | None = None) -> None:
    """토큰 저장 (암호화). refresh_token이 None이면 이미 있던 값을 유지한다."""
    exp = expires_at if isinstance(expires_at, str) else from_dt(expires_at)
    with session_scope() as s:
        g = s.get(GoogleConnection, user_id)
        if g is None:
            g = GoogleConnection(user_id=user_id, connected_at=now())
            s.add(g)
        g.access_token_enc, g.token_expires_at = encrypt_text(access_token), exp
        if refresh_token is not None:
            g.refresh_token_enc = encrypt_text(refresh_token)
        if google_account_id is not None:
            g.google_account_id = google_account_id
        if google_email is not None:
            g.google_email_enc = encrypt_text(google_email)


def get_google_tokens(user_id: int) -> dict | None:
    """{access_token, refresh_token, expires_at(UTC 문자열)}. 연결 안 했으면 None. 토큰은 FE로 보내지 않는다."""
    with session_scope() as s:
        g = s.get(GoogleConnection, user_id)
        if g is None:
            return None
        return {"access_token": decrypt_text(g.access_token_enc), "refresh_token": decrypt_text(g.refresh_token_enc),
                "expires_at": g.token_expires_at, "connected_at": g.connected_at}


def delete_google_connection(user_id: int) -> bool:
    """연결 해제 (토큰이 취소됐을 때 등)."""
    with session_scope() as s:
        return s.execute(delete(GoogleConnection).where(GoogleConnection.user_id == user_id)).rowcount > 0


def get_exported_events(user_id: int, event_ids: list[int] | None = None) -> dict[int, str]:
    """이미 Google에 넣은 일정 {event_id: google_event_id} (중복 등록 방지)."""
    q = select(CalendarExport.schedule_id, CalendarExport.google_event_id).where(CalendarExport.user_id == user_id)
    if event_ids is not None:
        q = q.where(CalendarExport.schedule_id.in_(set(event_ids)))
    with session_scope() as s:
        return dict(s.execute(q).all())


def record_export(user_id: int, event_id: int, google_event_id: str) -> None:
    """Google 등록 성공 기록. 다시 넣으면 google_event_id를 바꾼다."""
    with session_scope() as s:
        c = s.get(CalendarExport, (user_id, event_id))
        if c is None:
            s.add(CalendarExport(user_id=user_id, schedule_id=event_id, google_event_id=google_event_id,
                                 exported_at=now()))
        else:
            c.google_event_id, c.exported_at = google_event_id, now()
