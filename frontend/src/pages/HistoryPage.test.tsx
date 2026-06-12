import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { HistoryPage } from "./HistoryPage";
import { renderWithProviders } from "../test/utils";
import { api, ApiError } from "../api/client";

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

// Keep the real ApiError class: the page uses `instanceof ApiError` to detect
// a 409 from GET written.
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      getHistory: vi.fn(),
      checkHistory: vi.fn(),
      readd: vi.fn(),
      listSchedules: vi.fn(),
      getConfig: vi.fn(),
      getWritten: vi.fn(),
      unconfirm: vi.fn(),
      unskip: vi.fn(),
    },
  };
});

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
  (api.getWritten as ReturnType<typeof vi.fn>).mockResolvedValue({
    path: "/ledger/sprout.bean",
    text: '2026-05-01 * "Rent" "monthly rent" ; hand-edited\n  sprout-id: "sch1-20260501"\n',
  });
  (api.unconfirm as ReturnType<typeof vi.fn>).mockResolvedValue({
    ...confirmedOcc,
    status: "pending",
    written_path: null,
    confirmed_at: null,
  });
  (api.unskip as ReturnType<typeof vi.fn>).mockResolvedValue({
    ...skippedOcc,
    status: "pending",
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

test("edit dialog shows the written block plus warning, then unconfirms", async () => {
  mockAll();
  const user = userEvent.setup();
  renderWithProviders(<HistoryPage />);

  await user.click(
    await screen.findByRole("button", { name: /edit in inbox/i })
  );

  // The exact ledger text (manual edits included) and the loss warning.
  expect(await screen.findByText(/hand-edited/)).toBeInTheDocument();
  expect(screen.getByText(/manual edits in this text are deleted/i)).toBeInTheDocument();
  // The file name shows in the row AND in the dialog description.
  expect(screen.getAllByText(/sprout\.bean/).length).toBeGreaterThan(1);
  expect(api.getWritten).toHaveBeenCalledWith(11);

  await user.click(
    screen.getByRole("button", { name: /delete & move to inbox/i })
  );
  await waitFor(() => expect(api.unconfirm).toHaveBeenCalledWith(11));
  // Dialog closes on success.
  await waitFor(() =>
    expect(
      screen.queryByText(/manual edits in this text are deleted/i)
    ).not.toBeInTheDocument()
  );
});

test("closes the edit dialog and refreshes the check on a 409", async () => {
  mockAll();
  (api.getWritten as ReturnType<typeof vi.fn>).mockRejectedValue(
    new ApiError(409, "transaction is not present in the ledger")
  );
  const user = userEvent.setup();
  renderWithProviders(<HistoryPage />);
  expect(await screen.findByText("confirmed")).toBeInTheDocument();
  expect(api.checkHistory).toHaveBeenCalledTimes(1);

  await user.click(screen.getByRole("button", { name: /edit in inbox/i }));

  // Dialog never settles open: it closes and the reconcile check re-runs.
  await waitFor(() => expect(api.checkHistory).toHaveBeenCalledTimes(2));
  expect(
    screen.queryByText(/manual edits in this text are deleted/i)
  ).not.toBeInTheDocument();
  expect(api.unconfirm).not.toHaveBeenCalled();
});

test("missing row offers re-add and move back to inbox", async () => {
  mockAll({ missing: [11] });
  const user = userEvent.setup();
  renderWithProviders(<HistoryPage />);

  expect(await screen.findByText(/missing from ledger/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /re-add/i })).toBeInTheDocument();
  // No dialog for the missing variant — nothing is deleted.
  await user.click(
    screen.getByRole("button", { name: /move back to inbox/i })
  );
  await waitFor(() => expect(api.unconfirm).toHaveBeenCalledWith(11));
  expect(api.getWritten).not.toHaveBeenCalled();
});

test("skipped row unskips on click", async () => {
  mockAll();
  const user = userEvent.setup();
  renderWithProviders(<HistoryPage />);

  await user.click(await screen.findByRole("button", { name: /unskip/i }));
  await waitFor(() => expect(api.unskip).toHaveBeenCalledWith(12));
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
