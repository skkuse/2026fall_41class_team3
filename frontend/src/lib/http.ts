type ErrorBody = { code?: string; message?: string; retry_after?: number };

export class ApiError extends Error {
  status: number;
  body: ErrorBody;

  constructor(status: number, message: string, body: ErrorBody = {}) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
  });
  if (response.status === 204) return undefined as T;

  const data = await response.json().catch(() => null);
  if (!response.ok || !data) {
    throw new ApiError(
      response.status,
      data?.message ?? "서버에 연결할 수 없습니다.",
      data ?? {},
    );
  }
  return data as T;
}
