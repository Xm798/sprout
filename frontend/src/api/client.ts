import type {
  AppConfig,
  ConfirmBody,
  Occurrence,
  Schedule,
  ScheduleCreate,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function http<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers ?? {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listSchedules: () => http<Schedule[]>("/schedules"),
  createSchedule: (body: ScheduleCreate) =>
    http<Schedule>("/schedules", { method: "POST", body: JSON.stringify(body) }),
  deleteSchedule: (id: number) =>
    http<{ ok: boolean }>(`/schedules/${id}`, { method: "DELETE" }),

  getInbox: () => http<Occurrence[]>("/inbox"),
  preview: (id: number) => http<{ text: string }>(`/inbox/${id}/preview`),
  confirm: (id: number, body: ConfirmBody) =>
    http<Occurrence>(`/inbox/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  skip: (id: number) => http<Occurrence>(`/inbox/${id}/skip`, { method: "POST" }),

  accounts: () => http<string[]>("/accounts"),
  currencies: () => http<string[]>("/currencies"),
  getConfig: () => http<AppConfig>("/config"),
  updateConfig: (body: AppConfig) =>
    http<AppConfig>("/config", { method: "PUT", body: JSON.stringify(body) }),
};
