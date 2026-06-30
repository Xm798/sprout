import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

afterEach(() => vi.restoreAllMocks());

function mockFetch(body: unknown, ok = true, status = 200) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response);
}

describe("api client", () => {
  it("GETs /api/schedules", async () => {
    const f = mockFetch([{ id: 1 }]);
    const res = await api.listSchedules();
    expect(res).toEqual([{ id: 1 }]);
    expect(f.mock.calls[0][0]).toBe("/api/schedules");
  });

  it("POSTs createSchedule with a JSON body", async () => {
    const f = mockFetch({ id: 2 });
    await api.createSchedule({
      name: "X", payee: "", narration: "",
      postings: [
        { id: "a", account: "B", amount: "1", currency: "USD" },
        { id: "b", account: "A", amount: null, currency: null },
      ],
      interval_unit: "month", interval_count: 1, anchor_date: "2026-01-01",
      end_date: null, max_count: null, tags: "sprout", status: "active",
    });
    const [url, opts] = f.mock.calls[0];
    expect(url).toBe("/api/schedules");
    expect(opts?.method).toBe("POST");
    const body = JSON.parse(String(opts?.body));
    expect(body.name).toBe("X");
    expect(body.postings).toHaveLength(2);
  });

  it("POSTs previewTransient with override_amounts", async () => {
    const f = mockFetch({ text: "preview" });
    await api.previewTransient(3, { override_amounts: { p1: "9.99" } });
    const [url, opts] = f.mock.calls[0];
    expect(url).toBe("/api/inbox/3/preview");
    expect(opts?.method).toBe("POST");
    expect(JSON.parse(String(opts?.body)).override_amounts).toEqual({
      p1: "9.99",
    });
  });

  it("surfaces the FastAPI detail string on an error response", async () => {
    mockFetch({ detail: "amount 'abc' is not a number" }, false, 422);
    await expect(api.confirm(1, {})).rejects.toThrow(
      "amount 'abc' is not a number"
    );
  });
});

describe("notification settings client", () => {
  it("GET hits /api/config/notifications", async () => {
    const json = { notify_enabled: true, notify_channels: [] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(json), { status: 200 })));
    const out = await api.getNotifications();
    expect(out.notify_enabled).toBe(true);
    expect((fetch as any).mock.calls[0][0]).toContain("/api/config/notifications");
  });

  it("PUT sends settings body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response("{}", { status: 200 })));
    await api.updateNotifications({ notify_enabled: false, notify_lead_days: 1,
      notify_time: "08:00", notify_timezone: "UTC", notify_channels: [] });
    const [, opts] = (fetch as any).mock.calls[0];
    expect(opts.method).toBe("PUT");
  });
});
