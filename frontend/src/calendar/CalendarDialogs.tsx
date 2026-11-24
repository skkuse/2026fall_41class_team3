import { useEffect, useState } from "react";
import { Button } from "../components/ui/button";
import { AppModal } from "../components/AppModal";
import { NativeSelect } from "../components/ui/native-select";
import { ApiError } from "../lib/http";
import {
  exportEvent,
  listDepartmentChoices,
  webUrl,
  type CalendarEvent,
  type DepartmentChoice,
} from "./api";
import { eventPeriod } from "./dates";
import { calendarPreview } from "./previewData";

const calendarModal =
  "max-h-[calc(100dvh-2rem)] overflow-auto text-[#111] " +
  "[--color-accent:#f4f8f6] [--color-accent-foreground:#111] " +
  "[--color-border:var(--color-calendar-border)] [--color-input:var(--color-calendar-border)] " +
  "[--color-ring:var(--color-primary)] [&_h3]:m-0 [&_h3]:wrap-anywhere [&_p]:wrap-anywhere";

const facultyLabel = (department: DepartmentChoice) =>
  department.facultyName ?? "소속 미분류";

export function DepartmentSelector({
  activeId,
  onApply,
  onClose,
}: {
  activeId?: number;
  onApply: (department: DepartmentChoice) => void;
  onClose: () => void;
}) {
  const [choices, setChoices] = useState<DepartmentChoice[]>([]);
  const [faculty, setFaculty] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );

  useEffect(() => {
    const controller = new AbortController();
    listDepartmentChoices(controller.signal)
      .then((choices) => {
        if (controller.signal.aborted) return;
        setChoices(choices);
        const active = choices.find(
          (choice) => choice.departmentId === activeId,
        );
        setFaculty(active ? facultyLabel(active) : "");
        setDepartmentId(active ? String(active.departmentId) : "");
        setStatus("ready");
      })
      .catch(() => {
        if (!controller.signal.aborted) setStatus("error");
      });
    return () => controller.abort();
  }, [activeId, attempt]);

  const faculties = [...new Set(choices.map(facultyLabel))];
  const departments = choices.filter(
    (choice) => facultyLabel(choice) === faculty,
  );
  const selected = departments.find(
    (department) => String(department.departmentId) === departmentId,
  );
  return (
    <AppModal
      className={calendarModal}
      title="조회 학과 선택"
      onClose={onClose}
    >
      {status === "loading" && (
        <p role="status">학과 목록을 불러오는 중입니다.</p>
      )}
      {status === "error" && (
        <p role="alert">
          학과 목록을 불러오지 못했습니다.{" "}
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setStatus("loading");
              setAttempt(attempt + 1);
            }}
          >
            다시 시도
          </Button>
        </p>
      )}
      {status === "ready" && (
        <>
          {choices.length === 0 && (
            <p role="status">선택할 수 있는 학과가 없습니다.</p>
          )}
          <label className="grid gap-[7px] text-[0.85rem] font-semibold">
            단과대학 / 학부대학
            <NativeSelect
              disabled={!faculties.length}
              value={faculty}
              onChange={(event) => {
                setFaculty(event.target.value);
                setDepartmentId("");
              }}
            >
              <option value="">대학을 선택해 주세요</option>
              {faculties.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </NativeSelect>
          </label>
          <label className="grid gap-[7px] text-[0.85rem] font-semibold">
            학과 / 전공 / 계열
            <NativeSelect
              disabled={!departments.length}
              value={departmentId}
              onChange={(event) => setDepartmentId(event.target.value)}
            >
              <option value="">학과를 선택해 주세요</option>
              {departments.map((department) => (
                <option
                  key={department.departmentId}
                  value={department.departmentId}
                >
                  {department.departmentName}
                </option>
              ))}
            </NativeSelect>
          </label>
          <p className="m-0 text-[0.82rem] text-[#414141]">
            현재 캘린더의 조회 학과만 변경됩니다.
          </p>
        </>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>
          취소
        </Button>
        <Button
          type="button"
          disabled={!selected}
          onClick={() => {
            if (selected) onApply(selected);
          }}
        >
          적용
        </Button>
      </div>
    </AppModal>
  );
}

const googleCalendarEnabled = false;

const uncertain =
  "등록 결과를 확인하지 못했습니다. Google Calendar에서 일정이 추가됐는지 확인한 후, 없다면 다시 시도해 주세요.";

export function EventDetail({
  event,
  kind,
  onClose,
  onGoogleConnect,
  onLogin,
}: {
  event: CalendarEvent;
  kind: { label: string; className: string };
  onClose: () => void;
  onGoogleConnect: (url: string) => void;
  onLogin: () => void;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ message: string; link?: string }>();

  async function addToGoogle() {
    setPending(true);
    setResult(undefined);
    try {
      const response = await exportEvent(event.eventId);
      if (response.status === "authorization_required") {
        const url = webUrl(response.authorizationUrl);
        if (url) onGoogleConnect(url);
        else setResult({ message: "Google 연결 주소를 확인할 수 없습니다." });
        return;
      }
      const item = response.results.find(
        (item) => item.eventId === event.eventId,
      );
      if (!item) setResult({ message: uncertain });
      else if (item.status === "failed")
        setResult({
          message: item.error?.code.includes("UNKNOWN")
            ? uncertain
            : (item.error?.message ?? "일정을 추가하지 못했습니다."),
        });
      else
        setResult({
          message: item.alreadyAdded
            ? "이미 추가된 일정입니다."
            : "Google Calendar에 일정을 추가했습니다.",
          link: webUrl(item.htmlLink),
        });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        onLogin();
      } else {
        setResult({
          message:
            error instanceof ApiError && error.status >= 400
              ? error.message
              : uncertain,
        });
      }
    } finally {
      setPending(false);
    }
  }

  const image = webUrl(event.imageUrl);
  const source = webUrl(event.sourceUrl);
  return (
    <AppModal
      className={calendarModal}
      title={event.eventTitle}
      tag={
        <span
          className={`rounded border border-solid border-calendar-grid bg-white px-2 py-[3px] text-[0.75rem] whitespace-nowrap text-(--event-dot) ${kind.className}`}
        >
          {kind.label}
        </span>
      }
      onClose={onClose}
    >
      {event.noticeTitle && (
        <p className="m-0 text-[0.82rem] text-[#414141]">
          공지 제목 · {event.noticeTitle}
        </p>
      )}
      <div className="flex flex-wrap gap-3.5 border-t border-solid border-calendar-border pt-[13px]">
        <dl className="m-0 grid flex-[1_1_240px] grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-[7px] text-[0.86rem] [&_dt]:font-[650] [&_dt]:text-[#252525] [&_dd]:m-0 [&_dd]:wrap-anywhere">
          <dt>일정</dt>
          <dd>{eventPeriod(event.startAt, event.endAt, event.isAllDay)}</dd>
          <dt>장소</dt>
          <dd>{event.location ?? "미기재"}</dd>
          <dt>주최</dt>
          <dd>{event.organizer ?? "미기재"}</dd>
          <dt>참여 대상</dt>
          <dd>{event.targetAudience ?? "미기재"}</dd>
        </dl>
        {image && !imageFailed && (
          <img
            className="max-h-[150px] w-[min(100%,130px)] self-start object-contain"
            src={image}
            alt="공지 대표 이미지"
            onError={() => setImageFailed(true)}
          />
        )}
      </div>
      {event.summary && (
        <section className="grid gap-1.5 border-t border-solid border-calendar-border pt-[13px] text-[0.88rem] leading-[1.6]">
          <h3>일정 요약</h3>
          <p className="m-0 whitespace-pre-wrap">{event.summary}</p>
        </section>
      )}
      {result && (
        <p
          className="my-3 rounded-md border border-solid border-calendar-border bg-white px-3 py-2.5 text-[0.84rem] text-[#252525]"
          role="status"
        >
          {result.message}{" "}
          {result.link && (
            <a href={result.link} target="_blank" rel="noreferrer">
              Google에서 보기
            </a>
          )}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>
          닫기
        </Button>
        {source && (
          <Button asChild variant="outline">
            <a href={source} target="_blank" rel="noreferrer">
              원문 보기 ↗
            </a>
          </Button>
        )}
        <Button
          type="button"
          disabled={!googleCalendarEnabled || pending}
          onClick={
            !googleCalendarEnabled
              ? undefined
              : calendarPreview
                ? () =>
                    setResult({
                      message:
                        "예시 일정은 Google Calendar에 등록할 수 없습니다.",
                    })
                : addToGoogle
          }
        >
          {pending ? "추가 중…" : "Google Calendar에 추가"}
        </Button>
      </div>
    </AppModal>
  );
}
