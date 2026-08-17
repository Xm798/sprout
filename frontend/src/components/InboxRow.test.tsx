import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { InboxRow } from "./InboxRow";
import { renderWithProviders } from "../test/utils";
import { api } from "../api/client";
import type { Occurrence, Schedule } from "../api/types";

vi.mock("../api/client", () => ({
  api: {
    previewTransient: vi.fn().mockResolvedValue({ text: "2026-06-15 * \"Spotify\"\n" }),
    confirm: vi.fn().mockResolvedValue({ id: 1, status: "confirmed" }),
    skip: vi.fn().mockResolvedValue({ id: 1, status: "skipped" }),
    markPaidOutside: vi.fn().mockResolvedValue({ id: 2, status: "confirmed" }),
  },
}));

afterEach(() => vi.clearAllMocks());

const occurrence: Occurrence = {
  id: 1, schedule_id: 7, due_date: "2026-06-15", status: "pending",
  override_amounts: {}, override_date: null, override_narration: null,
  written_path: null, sprout_id: "sch7-20260615", confirmed_at: null,
};

const schedule: Schedule = {
  id: 7, name: "Spotify", payee: "Spotify AB", narration: "sub",
  postings: [
    { id: "p1", account: "Expenses:Subscription", amount: "15.00", currency: "USD" },
    { id: "p2", account: "Assets:CreditCard", amount: null, currency: null },
  ],
  headline_amount: "15.00", headline_currency: "USD",
  interval_unit: "month", interval_count: 1, anchor_date: "2026-01-15",
  end_date: null, max_count: null, tags: "sprout", status: "active",
  created_at: "", updated_at: "",
};

test("shows the schedule name and headline amount", () => {
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  expect(screen.getByText("Spotify")).toBeInTheDocument();
  expect(screen.getByText(/15\.00/)).toBeInTheDocument();
});

test("a stored override is preferred over the headline default", () => {
  const overridden: Occurrence = { ...occurrence, override_amounts: { p1: "20.00" } };
  renderWithProviders(<InboxRow occurrence={overridden} schedule={schedule} />);
  expect(screen.getByText(/20\.00/)).toBeInTheDocument();
});

test("confirm calls the api with an empty body by default", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  await user.click(screen.getByRole("button", { name: /^confirm$/i }));
  await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
  expect(api.confirm).toHaveBeenCalledWith(1, {});
});

test("editing a leg sends override_amounts keyed by that leg's posting id", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  await user.click(screen.getByRole("button", { name: /preview/i }));
  await user.type(screen.getByLabelText("Subscription"), "20.00");
  await user.click(screen.getByRole("button", { name: /^confirm$/i }));
  await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
  expect(api.confirm).toHaveBeenCalledWith(1, {
    override_amounts: { p1: "20.00" },
  });
});

test("blank auto-balance leg's input is disabled and shows the derived amount", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  await user.click(screen.getByRole("button", { name: /preview/i }));
  const input = screen.getByLabelText("CreditCard");
  expect(input).toBeDisabled();
  expect(input).toHaveAttribute("placeholder", "-15");
});

test("typing into an explicit leg keeps the derived placeholder live", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  await user.click(screen.getByRole("button", { name: /preview/i }));
  await user.type(screen.getByLabelText("Subscription"), "20.00");
  expect(screen.getByLabelText("CreditCard")).toHaveAttribute("placeholder", "-20");
});

test("skip calls the api", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  await user.click(screen.getByRole("button", { name: /skip/i }));
  await waitFor(() => expect(api.skip).toHaveBeenCalledWith(1));
});

test("expanding shows the .bean preview", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  await user.click(screen.getByRole("button", { name: /preview/i }));
  expect(await screen.findByText(/2026-06-15 \* "Spotify"/)).toBeInTheDocument();
});

const payrollSchedule: Schedule = {
  ...schedule,
  id: 8,
  name: "Payroll",
  postings: [
    { id: "s1", account: "Income:Salary", amount: "-10000", currency: "CNY" },
    { id: "s2", account: "Expenses:Tax", amount: "1000", currency: "CNY" },
    { id: "s3", account: "Expenses:Social", amount: "500", currency: "CNY" },
    { id: "s4", account: "Assets:Bank:8888", amount: null, currency: null },
  ],
  headline_amount: "-10000",
  headline_currency: "CNY",
};

test("multi-posting: net amount, both sides, +N badge", () => {
  renderWithProviders(
    <InboxRow occurrence={{ ...occurrence, schedule_id: 8 }} schedule={payrollSchedule} />
  );
  expect(screen.getByText(/8,500\.00/)).toBeInTheDocument(); // net to bank, not -10000
  expect(screen.getByText("Salary")).toBeInTheDocument(); // source leaf
  expect(screen.getByText("Tax")).toBeInTheDocument(); // first destination (mobile cap = 1)
  expect(screen.getByText("+2")).toBeInTheDocument(); // Social + Bank folded
});

test("two-leg direction reads fund account → expense account", () => {
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  const src = screen.getByText("CreditCard");
  const dst = screen.getByText("Subscription");
  expect(
    src.compareDocumentPosition(dst) & Node.DOCUMENT_POSITION_FOLLOWING
  ).toBeTruthy();
});

test("amount input placeholder shows the editable leg's own amount, not the net", async () => {
  const user = userEvent.setup();
  renderWithProviders(
    <InboxRow occurrence={{ ...occurrence, schedule_id: 8 }} schedule={payrollSchedule} />
  );
  await user.click(screen.getByRole("button", { name: /preview/i }));
  expect(screen.getByLabelText("Salary")).toHaveAttribute("placeholder", "-10000");
});

const rentSchedule: Schedule = {
  ...schedule,
  id: 10,
  name: "Rent",
  postings: [
    { id: "r1", account: "Expenses:Rent", amount: "3000", currency: "CNY" },
    { id: "r2", account: "Assets:Bank", amount: "-3000", currency: "CNY" },
  ],
  headline_amount: "3000",
  headline_currency: "CNY",
};

const rentOccurrence: Occurrence = {
  id: 3, schedule_id: 10, due_date: "2026-06-15", status: "pending",
  override_amounts: {}, override_date: null, override_narration: null,
  written_path: null, sprout_id: "sch10-20260615", confirmed_at: null,
};

test("all-explicit legs: editing only the second leg overrides only that leg", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={rentOccurrence} schedule={rentSchedule} />);
  await user.click(screen.getByRole("button", { name: /preview/i }));
  await user.type(screen.getByLabelText("Bank"), "-3100");
  await user.click(screen.getByRole("button", { name: /^confirm$/i }));
  await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
  expect(api.confirm).toHaveBeenCalledWith(3, {
    override_amounts: { r2: "-3100" },
  });
});

test("all-explicit legs: editing both legs overrides both", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={rentOccurrence} schedule={rentSchedule} />);
  await user.click(screen.getByRole("button", { name: /preview/i }));
  await user.type(screen.getByLabelText("Rent"), "3100");
  await user.type(screen.getByLabelText("Bank"), "-3100");
  await user.click(screen.getByRole("button", { name: /^confirm$/i }));
  await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
  expect(api.confirm).toHaveBeenCalledWith(3, {
    override_amounts: { r1: "3100", r2: "-3100" },
  });
});

// ── loan occurrence ───────────────────────────────────────────────────────────

const loanSchedule: Schedule = {
  id: 9,
  name: "Mortgage",
  payee: "Bank",
  narration: "monthly mortgage",
  kind: "loan",
  postings: [
    { id: "p",   account: "Liabilities:Mortgage",       amount: null, currency: "USD", role: "principal" },
    { id: "i",   account: "Expenses:Mortgage:Interest", amount: null, currency: "USD", role: "interest" },
    { id: "pay", account: "Assets:Bank:Checking",       amount: null, currency: "USD", role: "payment" },
  ],
  headline_amount: "536.82",
  headline_currency: "USD",
  interval_unit: "month",
  interval_count: 1,
  anchor_date: "2026-01-15",
  end_date: null,
  max_count: null,
  tags: "sprout",
  status: "active",
  created_at: "",
  updated_at: "",
};

const loanOccurrence: Occurrence = {
  id: 2, schedule_id: 9, due_date: "2026-06-15", status: "pending",
  override_amounts: {}, override_date: null, override_narration: null,
  written_path: null, sprout_id: "sch9-20260615", confirmed_at: null,
};

test("loan InboxRow shows paid-outside button, not skip", () => {
  renderWithProviders(<InboxRow occurrence={loanOccurrence} schedule={loanSchedule} />);
  expect(screen.queryByRole("button", { name: /^skip$/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /paid outside/i })).toBeInTheDocument();
});

test("clicking paid-outside calls the api", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={loanOccurrence} schedule={loanSchedule} />);
  await user.click(screen.getByRole("button", { name: /paid outside/i }));
  await waitFor(() => expect(api.markPaidOutside).toHaveBeenCalledWith(2));
});

test("overdue loan occurrence shows needs-attention badge", () => {
  const overdue: Occurrence = { ...loanOccurrence, due_date: "2020-01-01" };
  renderWithProviders(<InboxRow occurrence={overdue} schedule={loanSchedule} />);
  expect(screen.getByText("Needs attention")).toBeInTheDocument();
});

test("non-overdue loan occurrence does not show needs-attention badge", () => {
  // A far-future due date is never overdue.
  const future: Occurrence = { ...loanOccurrence, due_date: "2099-12-31" };
  renderWithProviders(<InboxRow occurrence={future} schedule={loanSchedule} />);
  expect(screen.queryByText("Needs attention")).not.toBeInTheDocument();
});

test("loan schedule: every amount input is disabled", () => {
  // Loan rows start expanded, all three legs are blank/auto-balance with no
  // derivable amount (loanSchedule.postings has 3 entries: p, i, pay).
  renderWithProviders(<InboxRow occurrence={loanOccurrence} schedule={loanSchedule} />);
  const amountInputs = screen
    .getAllByRole("textbox")
    .filter((el) => el.id.includes("-amount-"));
  expect(amountInputs).toHaveLength(loanSchedule.postings.length);
  amountInputs.forEach((el) => {
    expect(el).toBeDisabled();
    expect(el).toHaveAttribute("placeholder", "—");
  });
});
