import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SchedulesPage } from "./SchedulesPage";
import { renderWithProviders } from "../test/utils";
import { api } from "../api/client";
import type { Schedule } from "../api/types";

const spotify: Schedule = {
  id: 7,
  name: "Spotify",
  narration: "sub",
  interval_unit: "month",
  interval_count: 1,
  anchor_date: "2026-01-15",
  end_date: null,
  max_count: 6,
  tags: "sprout",
  status: "active",
  target_file: null,
  postings: [
    { id: "main", account: "Expenses:Subscription", amount: "15.00", currency: "USD" },
    { id: "bal", account: "Assets:CreditCard", amount: null, currency: null },
  ],
  headline_amount: "15.00",
  headline_currency: "USD",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

vi.mock("../api/client", () => ({
  api: {
    listSchedules: vi.fn(() => Promise.resolve([spotify])),
    deleteSchedule: vi.fn().mockResolvedValue({ ok: true }),
    updateSchedule: vi.fn(() => Promise.resolve(spotify)),
    accounts: vi.fn().mockResolvedValue(["Assets:CreditCard", "Expenses:Subscription"]),
    currencies: vi.fn().mockResolvedValue(["USD"]),
    beanFiles: vi.fn().mockResolvedValue([]),
    getConfig: vi.fn().mockResolvedValue({ id: 1, default_currency: "USD" }),
  },
}));

afterEach(() => vi.clearAllMocks());

test("pencil button opens a prefilled edit form and saves via PUT", async () => {
  const user = userEvent.setup();
  renderWithProviders(<SchedulesPage />);

  await user.click(await screen.findByRole("button", { name: /edit spotify/i }));
  expect(await screen.findByLabelText(/^name$/i)).toHaveValue("Spotify");

  await user.click(screen.getByRole("button", { name: /save changes/i }));
  await waitFor(() =>
    expect(api.updateSchedule).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ name: "Spotify" })
    )
  );
});
