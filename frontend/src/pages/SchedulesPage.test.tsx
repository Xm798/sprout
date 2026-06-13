import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SchedulesPage } from "./SchedulesPage";
import { makeSchedule, renderWithProviders } from "../test/utils";
import { api } from "../api/client";

const spotify = makeSchedule();
const payroll = makeSchedule({
  id: 8,
  name: "Payroll",
  narration: "monthly payroll",
  postings: [
    { id: "s1", account: "Income:Salary", amount: "-10000", currency: "CNY" },
    { id: "s2", account: "Expenses:Tax", amount: "1000", currency: "CNY" },
    { id: "s3", account: "Expenses:Social", amount: "500", currency: "CNY" },
    { id: "s4", account: "Assets:Bank:8888", amount: null, currency: null },
  ],
  headline_amount: "-10000",
  headline_currency: "CNY",
});

vi.mock("../api/client", () => ({
  api: {
    listSchedules: vi.fn(() => Promise.resolve([spotify, payroll])),
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

  const editButton = await screen.findByRole("button", { name: /edit spotify/i });
  await user.click(editButton);
  expect(await screen.findByLabelText(/^name$/i)).toHaveValue("Spotify");

  await user.click(screen.getByRole("button", { name: /save changes/i }));
  await waitFor(() =>
    expect(api.updateSchedule).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ name: "Spotify" })
    )
  );
  await waitFor(() =>
    expect(screen.queryByLabelText(/^name$/i)).not.toBeInTheDocument()
  );
  // The controlled dialog has no Radix trigger; onCloseAutoFocus must hand
  // focus back to the pencil button.
  expect(editButton).toHaveFocus();
});

test("escape closes the edit form and returns focus to the pencil button", async () => {
  const user = userEvent.setup();
  renderWithProviders(<SchedulesPage />);

  const editButton = await screen.findByRole("button", { name: /edit spotify/i });
  await user.click(editButton);
  await screen.findByLabelText(/^name$/i);

  await user.keyboard("{Escape}");
  await waitFor(() =>
    expect(screen.queryByLabelText(/^name$/i)).not.toBeInTheDocument()
  );
  expect(editButton).toHaveFocus();
});

test("schedule card shows full-path flow, +N badge, and net amount", async () => {
  renderWithProviders(<SchedulesPage />);
  expect(await screen.findByText("Payroll")).toBeInTheDocument();
  expect(screen.getByText("Income:Salary")).toBeInTheDocument(); // full path, not leaf
  expect(screen.getByText("Expenses:Tax")).toBeInTheDocument(); // first destination (mobile cap)
  expect(screen.getByText("+2")).toBeInTheDocument(); // Social + Bank folded
  expect(screen.getByText(/8,500\.00/)).toBeInTheDocument(); // net, not -10000
});
