const timeZone = "Asia/Seoul";
const monthFormat = new Intl.DateTimeFormat("sv-SE", {
  timeZone,
  year: "numeric",
  month: "2-digit",
});
const dayFormat = new Intl.DateTimeFormat("sv-SE", {
  timeZone,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
export const seoulDay = (date: Date) => dayFormat.format(date);
const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  timeZone,
  dateStyle: "medium",
});
const timeFormat = new Intl.DateTimeFormat("ko-KR", {
  timeZone,
  dateStyle: "medium",
  timeStyle: "short",
});
export const currentMonth = () => monthFormat.format(new Date());
export const monthDate = (month: string) => `${month}-01`;
export function shiftMonth(month: string, offset: number) {
  const date = new Date(`${monthDate(month)}T00:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() + offset);
  return date.toISOString().slice(0, 7);
}

export function eventPeriod(
  start: string,
  end: string | null,
  allDay: boolean,
) {
  if (!allDay) {
    const first = timeFormat.format(new Date(start));
    return end ? `${first} ~ ${timeFormat.format(new Date(end))}` : first;
  }
  const first = dateFormat.format(new Date(start));
  if (!end) return `${first} (종일)`;
  const last = new Date(end);
  last.setUTCDate(last.getUTCDate() - 1);
  const lastLabel = dateFormat.format(last);
  return `${first === lastLabel ? first : `${first} ~ ${lastLabel}`} (종일)`;
}
