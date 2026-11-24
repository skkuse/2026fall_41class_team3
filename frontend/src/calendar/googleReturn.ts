import type { Department } from "./api";

export const returnKey = "skku-calendar-google-return";
export type ReturnState = { department: Department; month: string };
export function getCalendarReturn(): ReturnState | null {
  try {
    return JSON.parse(sessionStorage.getItem(returnKey) ?? "null");
  } catch {
    return null;
  }
}
