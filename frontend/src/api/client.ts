import type {
  AppConfig,
  ConfirmBody,
  HistoryCheck,
  NotificationSettings,
  Occurrence,
  ParseBeanRequest,
  ParsedTransaction,
  PreviewBody,
  Schedule,
  ScheduleCreate,
  WrittenTransaction,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// FastAPI HTTPException bodies are `{"detail": "..."}`; surface that human-readable
// string instead of the raw JSON envelope. Falls back to the original text.
function errorDetail(text: string): string {
  try {
    const data = JSON.parse(text);
    if (typeof data?.detail === "string") return data.detail;
  } catch {
    // not JSON — use the raw text
  }
  return text;
}

async function http<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers ?? {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, errorDetail(text) || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listSchedules: () => http<Schedule[]>("/schedules"),
  createSchedule: (body: ScheduleCreate) =>
    http<Schedule>("/schedules", { method: "POST", body: JSON.stringify(body) }),
  updateSchedule: (id: number, body: ScheduleCreate) =>
    http<Schedule>(`/schedules/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteSchedule: (id: number) =>
    http<{ ok: boolean }>(`/schedules/${id}`, { method: "DELETE" }),
  parseTransaction: (body: ParseBeanRequest) =>
    http<ParsedTransaction>("/schedules/parse", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getInbox: () => http<Occurrence[]>("/inbox"),
  // POST preview renders with transient (unsaved) overrides so the inbox can
  // reflect edited amounts live; an empty body falls back to stored state.
  previewTransient: (id: number, body: PreviewBody) =>
    http<{ text: string }>(`/inbox/${id}/preview`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  confirm: (id: number, body: ConfirmBody) =>
    http<Occurrence>(`/inbox/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  skip: (id: number) => http<Occurrence>(`/inbox/${id}/skip`, { method: "POST" }),

  getHistory: () => http<Occurrence[]>("/history"),
  // Reconcile scan: which confirmed occurrences vanished from the ledger.
  checkHistory: () => http<HistoryCheck>("/history/check"),
  readd: (id: number) =>
    http<Occurrence>(`/history/${id}/readd`, { method: "POST" }),
  // The written block as it exists in the ledger, for the unconfirm dialog.
  getWritten: (id: number) =>
    http<WrittenTransaction>(`/history/${id}/written`),
  unconfirm: (id: number) =>
    http<Occurrence>(`/history/${id}/unconfirm`, { method: "POST" }),
  unskip: (id: number) =>
    http<Occurrence>(`/history/${id}/unskip`, { method: "POST" }),

  accounts: () => http<string[]>("/accounts"),
  currencies: () => http<string[]>("/currencies"),
  beanFiles: () => http<string[]>("/bean-files"),
  getConfig: () => http<AppConfig>("/config"),
  updateConfig: (body: AppConfig) =>
    http<AppConfig>("/config", { method: "PUT", body: JSON.stringify(body) }),

  getNotifications: () => http<NotificationSettings>("/config/notifications"),
  updateNotifications: (body: NotificationSettings) =>
    http<NotificationSettings>("/config/notifications", {
      method: "PUT", body: JSON.stringify(body),
    }),
  testNotification: (name?: string) =>
    http<Record<string, boolean | string>>("/config/notifications/test", {
      method: "POST", body: JSON.stringify({ channel_name: name ?? null }),
    }),
};
