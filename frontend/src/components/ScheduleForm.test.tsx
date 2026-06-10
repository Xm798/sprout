import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ScheduleForm } from "./ScheduleForm";
import { renderWithProviders } from "../test/utils";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    accounts: vi.fn().mockResolvedValue(["Assets:CreditCard", "Expenses:Subscription"]),
    currencies: vi.fn().mockResolvedValue(["USD", "CNY"]),
    createSchedule: vi.fn().mockResolvedValue({ id: 1 }),
  },
}));

afterEach(() => vi.clearAllMocks());

function todayIso() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

test("submits a new schedule with an amount leg and an auto-balance leg", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "Spotify");
  // Posting 1 is the amount (headline) leg; posting 2 is left blank to
  // auto-balance — the old "to / from" model.
  await user.type(screen.getByLabelText(/account 1/i), "Expenses:Subscription");
  await user.type(screen.getByLabelText(/amount 1/i), "15.00");
  await user.type(screen.getByLabelText(/account 2/i), "Assets:CreditCard");

  // The date field is a calendar popover; pick "Today".
  await user.click(screen.getByLabelText(/starting from/i));
  await user.click(await screen.findByRole("button", { name: /today/i }));

  await user.click(screen.getByRole("button", { name: /create schedule/i }));

  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg).toMatchObject({
    name: "Spotify",
    anchor_date: todayIso(),
    interval_unit: "month",
    interval_count: 1,
  });
  expect(arg.postings).toEqual([
    {
      id: expect.any(String),
      account: "Expenses:Subscription",
      amount: "15.00",
      currency: "USD",
    },
    {
      id: expect.any(String),
      account: "Assets:CreditCard",
      amount: null,
      currency: null,
    },
  ]);
});

test("adds and removes posting rows down to a floor of two", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  // Two rows by default; remove buttons disabled at the floor.
  expect(screen.getByLabelText(/remove posting 1/i)).toBeDisabled();

  await user.click(screen.getByRole("button", { name: /add posting/i }));
  expect(screen.getByLabelText(/account 3/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/remove posting 1/i)).toBeEnabled();

  await user.click(screen.getByLabelText(/remove posting 3/i));
  expect(screen.queryByLabelText(/account 3/i)).not.toBeInTheDocument();
});
