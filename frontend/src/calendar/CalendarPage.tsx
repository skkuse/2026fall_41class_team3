import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import luxonPlugin from "@fullcalendar/luxon3";
import koLocale from "@fullcalendar/core/locales/ko";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../components/ui/button";
import {
  listDepartments,
  listEvents,
  type CalendarEvent,
  type Department,
  type DepartmentChoice,
} from "./api";
import { DepartmentSelector, EventDetail } from "./CalendarDialogs";
import { currentMonth, monthDate, seoulDay, shiftMonth } from "./dates";
import { returnKey, type ReturnState } from "./googleReturn";
import "./calendar.css";

const kinds = [
  { label: "학사일정", className: "[--event-dot:#254a7d]" },
  { label: "학과 행사", className: "[--event-dot:#236b55]" },
  { label: "공지 마감", className: "[--event-dot:#963d49]" },
];

function eventKind(kind: string) {
  const key = kind.replace(/\s/g, "").toLowerCase();
  if (["academic", "academic_schedule", "학사일정"].includes(key))
    return kinds[0];
  if (["department", "department_event", "학과행사"].includes(key))
    return kinds[1];
  if (["deadline", "notice_deadline", "공지마감"].includes(key))
    return kinds[2];
  return { label: kind, className: "[--event-dot:#254a7d]" };
}

type Query = { id: number; month: string };
type Result = {
  query: Query;
  department?: Department;
  events?: CalendarEvent[];
  error?: string;
};

export default function CalendarPage({
  defaultId,
  visible,
  restored,
  googleNotice,
  onLogin,
}: {
  defaultId: number | null;
  visible: boolean;
  restored: ReturnState | null;
  googleNotice: string;
  onLogin: () => void;
}) {
  const calendar = useRef<FullCalendar>(null);
  const [selectedDay, setSelectedDay] = useState<string>();
  const [month, setMonth] = useState(() => restored?.month ?? currentMonth());
  const [selection, setSelection] = useState<{
    department: Department;
    query: Query;
    facultyName?: string;
  } | null>(() =>
    restored
      ? {
          department: restored.department,
          query: {
            id: restored.department.departmentId,
            month: currentMonth(),
          },
        }
      : null,
  );
  const [initialMonth] = useState(currentMonth);
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<Result>();
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [event, setEvent] = useState<CalendarEvent>();
  const [loginRequired, setLoginRequired] = useState(false);
  const initialQuery = useMemo<Query | null>(
    () => (defaultId === null ? null : { id: defaultId, month: initialMonth }),
    [defaultId, initialMonth],
  );
  const query = selection?.query ?? initialQuery;
  const [faculty, setFaculty] = useState<{
    departmentId: number;
    name: string;
  }>();
  const departmentId = query?.id;
  const selectedFaculty = selection?.facultyName;
  const selectedDepartment = selection?.department;

  useEffect(() => {
    if (departmentId === undefined || selectedFaculty) return;
    const controller = new AbortController();
    listDepartments(controller.signal)
      .then(({ faculties }) => {
        const match = faculties.find(({ departments }) =>
          departments.some(
            (department) => department.departmentId === departmentId,
          ),
        );
        if (match && !controller.signal.aborted)
          setFaculty({ departmentId, name: match.facultyName });
      })
      .catch(() => {
        // Department events can still load if the faculty directory is unavailable.
      });
    return () => controller.abort();
  }, [departmentId, selectedFaculty]);

  useEffect(() => {
    if (!query) return;
    const controller = new AbortController();
    listEvents(query.id, query.month, controller.signal, selectedDepartment)
      .then(({ events, ...department }) => {
        if (!controller.signal.aborted)
          setResult({ query, department, events });
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted)
          setResult({ query, error: error.message });
      });
    return () => controller.abort();
  }, [query, retry, selectedDepartment]);

  useEffect(() => {
    if (visible) calendar.current?.getApi().updateSize();
  }, [visible]);

  const response = result?.query === query ? result : undefined;
  const department = response?.department ?? selection?.department;
  const facultyName =
    selectedFaculty ??
    (faculty?.departmentId === departmentId ? faculty?.name : undefined);
  const outside =
    query &&
    (month < shiftMonth(query.month, -2) || month > shiftMonth(query.month, 2));
  const events = outside ? [] : (response?.events ?? []);
  const message = !query
    ? "학과를 선택해 주세요."
    : !response
      ? "일정을 불러오는 중입니다."
      : response.error
        ? `일정을 불러오지 못했습니다. ${response.error}`
        : outside
          ? "해당 월의 일정 데이터를 아직 받지 않았습니다."
          : !events.length
            ? "선택한 학과에 표시할 일정이 없습니다."
            : "";

  function goToMonth(next: string) {
    setSelectedDay(undefined);
    setMonth(next);
    calendar.current?.getApi().gotoDate(monthDate(next));
  }

  function applyDepartment({ facultyName, ...next }: DepartmentChoice) {
    setSelectorOpen(false);
    if (query?.id === next.departmentId && !response) return;
    setSelection({
      department: next,
      facultyName,
      query: { id: next.departmentId, month: currentMonth() },
    });
  }

  const monthLabel = `${month.slice(0, 4)}년 ${Number(month.slice(5))}월`;
  const firstWeekday = new Date(monthDate(month)).getUTCDay();
  const daysInMonth = new Date(`${monthDate(shiftMonth(month, 1))}T00:00:00Z`);
  daysInMonth.setUTCDate(0);
  const today = seoulDay(new Date());
  return (
    <section
      className="min-h-[calc(100vh-64px)] bg-white p-[clamp(18px,3.2vw,46px)] text-[#111] [--color-accent:#f4f8f6] [--color-accent-foreground:#111] [--color-border:var(--color-calendar-border)] [--color-ring:var(--color-primary)] max-[600px]:min-h-[calc(100vh-58px)] max-[600px]:px-2.5"
      aria-labelledby="calendar-heading"
    >
      <header className="mx-auto mb-[23px] max-w-[1340px]">
        <h1
          id="calendar-heading"
          className="m-0 mb-1.5 text-[clamp(1.4rem,3vw,1.95rem)] font-[750] tracking-[-0.04em] text-[#080808]"
        >
          학과 일정
        </h1>
        <p className="m-0 text-[0.9rem] leading-[1.6] text-[#414141] break-keep">
          학사일정과 학과 행사를 한눈에 보고, 놓치기 쉬운 마감도 챙겨보세요.
        </p>
      </header>
      {googleNotice && (
        <p
          className="my-3 rounded-md border border-solid border-calendar-border bg-white px-3 py-2.5 text-[0.84rem] text-[#252525]"
          role="status"
        >
          {googleNotice}
        </p>
      )}
      {loginRequired && (
        <p
          className="my-3 rounded-md border border-solid border-calendar-border bg-white px-3 py-2.5 text-[0.84rem] text-[#252525]"
          role="status"
        >
          Google Calendar에 추가하려면 서비스에 로그인해 주세요.
        </p>
      )}
      <div className="mx-auto grid max-w-[1340px] grid-cols-[246px_minmax(0,1fr)] items-start gap-5 max-[960px]:grid-cols-1">
        <aside
          className="grid gap-3.5 max-[960px]:grid-cols-[minmax(0,1fr)_minmax(0,246px)] max-[960px]:items-start max-[600px]:grid-cols-1"
          aria-label="학과와 날짜 선택"
        >
          <section className="min-w-0 rounded-[13px] border border-solid border-calendar-border bg-white grid gap-[11px] p-[17px]">
            <div className="flex items-center justify-between gap-2">
              <h2 className="m-0 text-[1.05rem] font-bold">조회 학과</h2>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-[0.75rem] text-primary"
                aria-label={query ? "학과 변경" : "학과 선택"}
                onClick={() => setSelectorOpen(true)}
              >
                {query ? "변경" : "선택"}
              </Button>
            </div>
            <dl className="m-0 grid gap-3 wrap-anywhere [&_dt]:text-[0.75rem] [&_dt]:text-[#666] [&_dd]:mx-0 [&_dd]:mt-1 [&_dd]:mb-0 [&_dd]:text-[0.8rem]">
              <div>
                <dt>단과대학 / 학부대학</dt>
                <dd>{facultyName ?? "—"}</dd>
              </div>
              <div>
                <dt>학과 / 전공 / 계열</dt>
                <dd>
                  {department?.departmentName ??
                    (query ? "기본 학과" : "선택된 학과 없음")}
                </dd>
              </div>
            </dl>
          </section>
          <section
            className="min-w-0 rounded-[13px] border border-solid border-calendar-border bg-white p-[17px] max-[600px]:px-2.5 max-[600px]:py-2"
            aria-label="미니 달력"
          >
            <div className="mb-2.5 flex items-center justify-between max-[600px]:hidden">
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => goToMonth(shiftMonth(month, -1))}
                className="bg-transparent hover:bg-icon-hover hover:text-neutral-700"
                aria-label="미니 달력 이전 달"
              >
                <ChevronLeft />
              </Button>
              <h2 className="m-0 text-[0.85rem]">{monthLabel}</h2>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => goToMonth(shiftMonth(month, 1))}
                className="bg-transparent hover:bg-icon-hover hover:text-neutral-700"
                aria-label="미니 달력 다음 달"
              >
                <ChevronRight />
              </Button>
            </div>
            <div className="grid grid-cols-7 items-center gap-0.5 text-center [&>span]:text-[0.7rem] [&>span]:leading-[1.8] max-[600px]:hidden">
              {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
                <span key={day}>{day}</span>
              ))}
              {Array.from({ length: firstWeekday }, (_, index) => (
                <span key={`blank-${index}`} aria-hidden="true" />
              ))}
              {Array.from({ length: daysInMonth.getUTCDate() }, (_, index) => {
                const day = index + 1;
                const date = `${month}-${String(day).padStart(2, "0")}`;
                return (
                  <Button
                    key={date}
                    variant="ghost"
                    type="button"
                    className="h-[30px] w-full min-w-0 p-0 text-[0.72rem] tabular-nums hover:bg-transparent hover:text-[#111] hover:underline hover:underline-offset-[3px] aria-pressed:underline aria-pressed:decoration-2 aria-pressed:underline-offset-[3px] aria-[current=date]:font-[750]"
                    aria-label={`${monthLabel} ${day}일`}
                    aria-current={today === date ? "date" : undefined}
                    aria-pressed={selectedDay === date}
                    onClick={() =>
                      setSelectedDay(selectedDay === date ? undefined : date)
                    }
                  >
                    {day}
                  </Button>
                );
              })}
            </div>
            <ul
              className="mt-3 mx-0 mb-0 flex flex-wrap gap-1 pt-3 pr-0 pb-0 pl-0 text-[0.66rem] max-[600px]:m-0 max-[600px]:p-0"
              aria-label="일정 유형"
            >
              {kinds.map((kind) => (
                <li
                  className={`flex items-center gap-[5px] rounded-full border border-solid border-calendar-grid bg-white px-1.5 py-1 ${kind.className}`}
                  key={kind.label}
                >
                  <span className="size-[7px] shrink-0 rounded-full bg-(--event-dot)" />
                  {kind.label}
                </li>
              ))}
            </ul>
          </section>
        </aside>
        <section
          className="min-w-0 rounded-[13px] border border-solid border-calendar-border bg-white p-[clamp(10px,2vw,24px)]"
          aria-labelledby="calendar-month-title"
        >
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex flex-wrap items-center gap-2.5">
              <CalendarDays
                className="size-[17px] text-primary"
                aria-hidden="true"
              />
              <h2
                id="calendar-month-title"
                className="m-0 text-[1.08rem]"
                aria-live="polite"
              >
                {monthLabel}
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-[5px]">
              <Button
                variant="outline"
                size="sm"
                onClick={() => goToMonth(currentMonth())}
              >
                오늘
              </Button>
              <Button
                variant="outline"
                size="icon-sm"
                onClick={() => goToMonth(shiftMonth(month, -1))}
                className="hover:bg-icon-hover hover:text-neutral-700"
                aria-label="이전 달"
              >
                <ChevronLeft />
              </Button>
              <Button
                variant="outline"
                size="icon-sm"
                onClick={() => goToMonth(shiftMonth(month, 1))}
                className="hover:bg-icon-hover hover:text-neutral-700"
                aria-label="다음 달"
              >
                <ChevronRight />
              </Button>
            </div>
          </div>
          {message && (
            <div
              className="my-3 rounded-md border border-solid border-calendar-border bg-white px-3 py-2.5 text-[0.84rem] text-[#252525] flex flex-wrap items-center gap-2.5"
              role={response?.error ? "alert" : "status"}
            >
              {message}
              {response?.error && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setResult(undefined);
                    setRetry(retry + 1);
                  }}
                >
                  다시 시도
                </Button>
              )}
            </div>
          )}
          <div className="calendar-grid">
            <FullCalendar
              ref={calendar}
              plugins={[dayGridPlugin, luxonPlugin]}
              locale={koLocale}
              initialView="dayGridMonth"
              initialDate={monthDate(month)}
              timeZone="Asia/Seoul"
              headerToolbar={false}
              fixedWeekCount={false}
              showNonCurrentDates={true}
              height="auto"
              dayCellContent={({ dayNumberText }) =>
                dayNumberText.replace("일", "")
              }
              dayCellClassNames={({ date }) =>
                seoulDay(date) === selectedDay ? ["calendar-day-selected"] : []
              }
              dayMaxEvents={3}
              events={events.map((item) => ({
                id: String(item.eventId),
                title: item.eventTitle,
                start: item.startAt,
                end: item.endAt ?? undefined,
                allDay: item.isAllDay,
                classNames: [eventKind(item.kind).className],
                extendedProps: { item },
              }))}
              eventContent={({ event, timeText }) => (
                <button
                  className="flex w-full min-w-0 cursor-pointer items-center gap-[5px] rounded-[5px] border border-solid border-calendar-grid border-s-[3px] border-s-(--event-dot) bg-white px-[5px] py-[3px] text-left text-[0.72rem] text-[#111] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#111] max-[600px]:gap-[3px] max-[600px]:px-0.5"
                  type="button"
                  onClick={() =>
                    setEvent(event.extendedProps.item as CalendarEvent)
                  }
                  title={event.title}
                >
                  <span
                    className="size-[7px] shrink-0 rounded-full bg-(--event-dot) max-[600px]:hidden"
                    aria-hidden="true"
                  />
                  {timeText && (
                    <span className="max-[600px]:hidden">{timeText}</span>
                  )}
                  <span className="truncate">{event.title}</span>
                </button>
              )}
            />
          </div>
        </section>
      </div>
      {selectorOpen && (
        <DepartmentSelector
          activeId={query?.id}
          onApply={applyDepartment}
          onClose={() => setSelectorOpen(false)}
        />
      )}
      {event && (
        <EventDetail
          key={event.eventId}
          event={event}
          kind={eventKind(event.kind)}
          onClose={() => setEvent(undefined)}
          onLogin={() => {
            setLoginRequired(true);
            setEvent(undefined);
            onLogin();
          }}
          onGoogleConnect={(url) => {
            if (department)
              sessionStorage.setItem(
                returnKey,
                JSON.stringify({ department, month }),
              );
            window.location.assign(url);
          }}
        />
      )}
    </section>
  );
}
