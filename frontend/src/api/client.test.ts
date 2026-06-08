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
      name: "X", narration: "", amount: "1", currency: "USD",
      from_account: "A", to_account: "B", interval_unit: "month",
      interval_count: 1, anchor_date: "2026-01-01", end_date: null,
      max_count: null, tags: "sprout", status: "active",
    });
    const [url, opts] = f.mock.calls[0];
    expect(url).toBe("/api/schedules");
    expect(opts?.method).toBe("POST");
    expect(JSON.parse(String(opts?.body)).name).toBe("X");
  });

  it("throws on a non-ok response", async () => {
    mockFetch({ detail: "bad" }, false, 422);
    await expect(api.confirm(1, {})).rejects.toThrow();
  });
});
