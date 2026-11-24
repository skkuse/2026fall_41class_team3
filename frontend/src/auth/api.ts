import { request } from "../lib/http";

export type User = { id: number; email: string; department_id: number | null };
export type Session = { user: User | null; needs_onboarding: boolean };
export type CatalogItem = { id: number; name: string };
type Address = { student_id: string; domain: number };

const json = (
  method: "POST" | "PUT",
  body: object,
  signal: AbortSignal,
): RequestInit => ({
  method,
  body: JSON.stringify(body),
  headers: { "Content-Type": "application/json" },
  signal,
});

export const getSession = (signal: AbortSignal) =>
  request<Session>("/api/me", { signal });
export const sendCode = (address: Address, signal: AbortSignal) =>
  request<{ expires_in: number; resend_after: number }>(
    "/api/auth/email-code",
    json("POST", address, signal),
  );
export const verifyCode = (
  address: Address,
  code: string,
  signal: AbortSignal,
) =>
  request<Session>(
    "/api/auth/verify",
    json("POST", { ...address, code }, signal),
  );
export const logout = () =>
  request<void>("/api/auth/logout", { method: "POST" });
export const departments = (signal: AbortSignal) =>
  request<{ items: CatalogItem[] }>("/api/departments", { signal });
export const interests = (signal: AbortSignal) =>
  request<{ items: CatalogItem[] }>("/api/interests", { signal });
type Profile = { user: User; interests: number[] };

export const getProfile = (signal: AbortSignal) =>
  request<Profile>("/api/me/profile", { signal });
export const saveProfile = (
  department_id: number,
  interests: number[],
  signal: AbortSignal,
) =>
  request<Profile>(
    "/api/me/profile",
    json("PUT", { department_id, interests }, signal),
  );
