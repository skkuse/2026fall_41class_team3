import type { CalendarEvent } from "./api";
import { shiftMonth } from "./dates";
import previewFaculties from "./previewDepartments.json";

export { previewFaculties };

export const calendarPreview = import.meta.env.VITE_CALENDAR_USE_API !== "true";

export const softwareDepartment = {
  departmentId: 50,
  departmentName: "소프트웨어학과",
};

type SampleEvent = Omit<
  CalendarEvent,
  "imageUrl" | "sourceUrl" | "targetAudience"
>;

export function previewEvents(month: string): CalendarEvent[] {
  const nextMonth = shiftMonth(month, 1);
  const samples: SampleEvent[] = [
    {
      eventId: 101,
      eventTitle: "수강철회 신청",
      noticeTitle: "수강철회 신청 기간 안내",
      startAt: `${month}-04`,
      endAt: `${month}-07`,
      isAllDay: true,
      kind: "academic",
      summary: "수강 중인 과목의 철회를 신청할 수 있는 기간입니다.",
      location: null,
      organizer: "학사운영팀",
    },
    {
      eventId: 102,
      eventTitle: "졸업 프로젝트 데모데이",
      noticeTitle: "소프트웨어학과 졸업 프로젝트 발표회 안내",
      startAt: `${month}-12T14:00:00+09:00`,
      endAt: `${month}-12T16:00:00+09:00`,
      isAllDay: false,
      kind: "department",
      summary:
        "졸업 프로젝트 팀의 발표와 시연을 보고, 팀원들과 질의응답을 나눕니다.",
      location: "제1공학관 세미나실",
      organizer: "소프트웨어학과",
    },
    {
      eventId: 103,
      eventTitle: "멘토링 신청 마감",
      noticeTitle: "선배 개발자 멘토링 참가자 모집",
      startAt: `${month}-19T23:59:00+09:00`,
      endAt: null,
      isAllDay: false,
      kind: "deadline",
      summary:
        "선배 개발자에게 진로와 프로젝트에 대한 조언을 받을 수 있는 멘토링 신청이 마감됩니다.",
      location: null,
      organizer: "소프트웨어학과 학생회",
    },
    {
      eventId: 104,
      eventTitle: "개발자 진로 특강",
      noticeTitle: "소프트웨어학과 진로 특강 안내",
      startAt: `${month}-25T15:00:00+09:00`,
      endAt: `${month}-25T16:30:00+09:00`,
      isAllDay: false,
      kind: "department",
      summary: "현직 개발자가 직무별 업무와 취업 준비 경험을 소개합니다.",
      location: "제1공학관 세미나실",
      organizer: "소프트웨어학과",
    },
    {
      eventId: 105,
      eventTitle: "학기 성적 열람",
      noticeTitle: "성적 열람 및 이의 신청 기간 안내",
      startAt: `${nextMonth}-08`,
      endAt: `${nextMonth}-11`,
      isAllDay: true,
      kind: "academic",
      summary: "과목별 성적을 확인하고 열람 기간에 이의 신청을 할 수 있습니다.",
      location: null,
      organizer: "학사운영팀",
    },
  ];

  return samples.map((event) => ({
    ...event,
    imageUrl: null,
    sourceUrl: null,
    targetAudience: "소프트웨어학과 재학생",
  }));
}
