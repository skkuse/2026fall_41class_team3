import { departments } from "../auth/api";
import { ApiError, request } from "../lib/http";
import {
  calendarPreview,
  previewEvents,
  previewFaculties,
  softwareDepartment,
} from "./previewData";

export type Department = { departmentId: number; departmentName: string };
export type Faculty = {
  facultyId: number;
  facultyName: string;
  departments: Department[];
};
export type CalendarEvent = {
  eventId: number;
  eventTitle: string;
  noticeTitle: string;
  startAt: string;
  endAt: string | null;
  isAllDay: boolean;
  kind: string;
  summary: string | null;
  location: string | null;
  organizer: string | null;
  targetAudience: string | null;
  imageUrl: string | null;
  sourceUrl: string | null;
};

export async function listDepartments(
  signal: AbortSignal,
): Promise<{ faculties: Faculty[] }> {
  if (calendarPreview) return { faculties: previewFaculties };
  return request("/api/calendar/departments", { signal });
}

export type DepartmentChoice = Department & { facultyName?: string };

export async function listDepartmentChoices(
  signal: AbortSignal,
): Promise<DepartmentChoice[]> {
  const { faculties } = await listDepartments(signal);
  const choices = faculties.flatMap(({ facultyName, departments }) =>
    departments.map((department) => ({ ...department, facultyName })),
  );
  if (!calendarPreview) return choices;

  try {
    const { items } = await departments(signal);
    return items.map(({ id, name }) => ({
      departmentId: id,
      departmentName: name,
      facultyName: choices.find(
        (choice) =>
          choice.departmentId === id && choice.departmentName === name,
      )?.facultyName,
    }));
  } catch (error) {
    if (signal.aborted) throw error;
    return choices;
  }
}

export async function listEvents(
  id: number,
  month: string,
  signal: AbortSignal,
  selected?: Department,
): Promise<Department & { events: CalendarEvent[] }> {
  if (calendarPreview) {
    const department =
      selected ??
      previewFaculties
        .flatMap((faculty) => faculty.departments)
        .find((department) => department.departmentId === id);
    if (!department) throw new ApiError(404, "학과를 찾을 수 없습니다.");
    return {
      ...department,
      events:
        department.departmentName === softwareDepartment.departmentName
          ? previewEvents(month)
          : [],
    };
  }
  return request(`/api/departments/${id}/events?month=${month}`, { signal });
}

type ExportResult =
  | { status: "authorization_required"; authorizationUrl: string }
  | {
      status: "success" | "partial_success" | "failed";
      results: {
        eventId: number;
        status: string;
        htmlLink: string | null;
        error: { code: string; message: string } | null;
        alreadyAdded: boolean | null;
      }[];
    };

export const exportEvent = (id: number) =>
  request<ExportResult>("/api/events/google-calendar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ eventIds: [id] }),
  });

export function webUrl(value: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (url.protocol === "https:" || url.protocol === "http:") return url.href;
  } catch {
    /* Ignore malformed URLs from the API. */
  }
}
