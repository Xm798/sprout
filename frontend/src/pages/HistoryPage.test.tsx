import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { HistoryPage } from "./HistoryPage";
import { renderWithProviders } from "../test/utils";
import { api } from "../api/client";

const schedule = {
  id: 1,
  name: "Rent",
  narration: "monthly rent",
  postings: [
    { id: "main", account: "Expenses:Housing:Rent", amount: "1000.00", currency: "USD" },
    { id: "bal", account: "Assets:Bank:Checking", amount: null },
  ],
  interval_unit: "month",
  interval_count: 1,
  anchor_date: "2026-01-01",
  tags: "sprout",
  status: "active",
  headline_amount: "1000.00",
  headline_currency: "USD",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

const confirmedOcc = {
  id: 11,
  schedule_id: 1,
  due_date: "2026-05-01",
  status: "confirmed",
  override_amounts: {},
  written_path: "/ledger/sprout.bean",
  sprout_id: "sch1-20260501",
  confirmed_at: "2026-05-01T09:00:00",
};

const skippedOcc = {
  id: 12,
  schedule_id: 1,
  due_date: "2026-04-01",
  status: "skipped",
  override_amounts: {},
};

vi.mock("../api/client", () => ({
  api: {
    getHistory: vi.fn(),
    checkHistory: vi.fn(),
    readd: vi.fn(),
    listSchedules: vi.fn(),
    getConfig: vi.fn(),
  },
}));

function mockAll({ missing = [] as number[] } = {}) {
  (api.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue([
    confirmedOcc,
    skippedOcc,
  ]);
  (api.checkHistory as ReturnType<typeof vi.fn>).mockResolvedValue({ missing });
  (api.listSchedules as ReturnType<typeof vi.fn>).mockResolvedValue([schedule]);
  (api.getConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
    id: 1, ledger_main_file: "/ledger/main.bean", ledger_root: "/ledger",
    write_mode: "single_file", single_file_name: "sprout.bean",
    month_file_template: "transactions/{year}/{year}-{month:02d}.bean",
    default_tag: "sprout", lookahead_days: 0,
  });
  (api.readd as ReturnType<typeof vi.fn>).mockResolvedValue({
    ...confirmedOcc,
  });
}

afterEach(() => vi.clearAllMocks());

test("renders confirmed and skipped rows with status badges", async () => {
  mockAll();
  renderWithProviders(<HistoryPage />);

  expect(await screen.findByText("confirmed")).toBeInTheDocument();
  expect(screen.getByText("skipped")).toBeInTheDocument();
  expect(screen.getAllByText("Rent")).toHaveLength(2);
  // Written file shown relative to the ledger root.
  expect(screen.getByText(/sprout\.bean/)).toBeInTheDocument();
  // Nothing missing -> no re-add affordance.
  expect(screen.queryByText(/missing from ledger/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /re-add/i })).not.toBeInTheDocument();
});

test("flags missing occurrences and re-adds them on click", async () => {
  mockAll({ missing: [11] });
  const user = userEvent.setup();
  renderWithProviders(<HistoryPage />);

  expect(await screen.findByText(/missing from ledger/i)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /re-add/i }));

  await waitFor(() => expect(api.readd).toHaveBeenCalledTimes(1));
  expect(api.readd).toHaveBeenCalledWith(11);
});

test("shows the check error without hiding history", async () => {
  mockAll();
  (api.checkHistory as ReturnType<typeof vi.fn>).mockRejectedValue(
    new Error("ledger main file not found")
  );
  renderWithProviders(<HistoryPage />);

  expect(await screen.findByText("confirmed")).toBeInTheDocument();
  expect(
    await screen.findByText(/ledger check failed/i)
  ).toBeInTheDocument();
});
