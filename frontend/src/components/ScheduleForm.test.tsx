import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ScheduleForm } from "./ScheduleForm";
import { makeSchedule, renderWithProviders } from "../test/utils";
import { api } from "../api/client";
import type { Posting, Schedule } from "../api/types";

vi.mock("../api/client", () => ({
  api: {
    accounts: vi.fn().mockResolvedValue(["Assets:CreditCard", "Expenses:Subscription"]),
    currencies: vi.fn().mockResolvedValue(["USD", "CNY"]),
    beanFiles: vi.fn().mockResolvedValue(["rent.bean", "loans/car.bean"]),
    // ScheduleForm only reads default_currency off the config.
    getConfig: vi.fn().mockResolvedValue({ id: 1, default_currency: "USD" }),
    createSchedule: vi.fn().mockResolvedValue({ id: 1 }),
    updateSchedule: vi.fn().mockResolvedValue({ id: 7 }),
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
      cost: null,
      price: null,
    },
    {
      id: expect.any(String),
      account: "Assets:CreditCard",
      amount: null,
      currency: null,
    },
  ]);
});

test("submits null target_file when the field is left empty", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "Spotify");
  await user.type(screen.getByLabelText(/account 1/i), "Expenses:Subscription");
  await user.type(screen.getByLabelText(/amount 1/i), "15.00");
  await user.type(screen.getByLabelText(/account 2/i), "Assets:CreditCard");
  await user.click(screen.getByLabelText(/starting from/i));
  await user.click(await screen.findByRole("button", { name: /today/i }));

  await user.click(screen.getByRole("button", { name: /create schedule/i }));

  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg.target_file).toBeNull();
});

test("submits the typed target_file and hints when it is a new file", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "Rent");
  await user.type(screen.getByLabelText(/account 1/i), "Expenses:Subscription");
  await user.type(screen.getByLabelText(/amount 1/i), "1500.00");
  await user.type(screen.getByLabelText(/account 2/i), "Assets:CreditCard");
  await user.click(screen.getByLabelText(/starting from/i));
  await user.click(await screen.findByRole("button", { name: /today/i }));

  await user.type(screen.getByLabelText(/target file/i), "housing.bean");
  // not in the mocked bean-files list -> new-file hint appears
  expect(
    await screen.findByText(/will be created and included/i)
  ).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /create schedule/i }));

  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg.target_file).toBe("housing.bean");
});

test("shows no new-file hint for an existing bean file", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  // Type a prefix and pick the existing file from the suggestion list — the
  // option appearing proves the bean-files query has resolved.
  await user.type(screen.getByLabelText(/target file/i), "rent");
  await user.click(await screen.findByRole("option", { name: /rent\.bean/i }));

  expect(screen.getByLabelText(/target file/i)).toHaveValue("rent.bean");
  expect(
    screen.queryByText(/will be created and included/i)
  ).not.toBeInTheDocument();
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

const existing = makeSchedule();

test("edit mode prefills fields and PUTs with preserved posting ids", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm schedule={existing} />);

  const name = screen.getByLabelText(/^name$/i);
  expect(name).toHaveValue("Spotify");
  expect(screen.getByLabelText(/amount 1/i)).toHaveValue("15.00");
  expect(screen.getByLabelText(/account 2/i)).toHaveValue("Assets:CreditCard");

  await user.clear(name);
  await user.type(name, "Spotify Family");
  await user.click(screen.getByRole("button", { name: /save changes/i }));

  await waitFor(() => expect(api.updateSchedule).toHaveBeenCalledTimes(1));
  expect(api.createSchedule).not.toHaveBeenCalled();
  const [id, body] = (api.updateSchedule as ReturnType<typeof vi.fn>).mock.calls[0];
  expect(id).toBe(7);
  expect(body.name).toBe("Spotify Family");
  // Stored posting ids must survive the round-trip so the backend keeps
  // per-leg overrides on untouched legs.
  expect(body.postings.map((p: Posting) => p.id)).toEqual(["main", "bal"]);
});

test("edit mode round-trips cost/price annotations the form can't edit", async () => {
  const user = userEvent.setup();
  const cost = { amount: "1.10", currency: "USD", total: false };
  const price = { amount: "7.50", currency: "USD", total: true };
  const withAnnotations: Schedule = {
    ...existing,
    postings: [
      { ...existing.postings[0], cost, price },
      existing.postings[1],
    ],
  };
  renderWithProviders(<ScheduleForm schedule={withAnnotations} />);

  await user.click(screen.getByRole("button", { name: /save changes/i }));

  await waitFor(() => expect(api.updateSchedule).toHaveBeenCalledTimes(1));
  const [, body] = (api.updateSchedule as ReturnType<typeof vi.fn>).mock.calls[0];
  expect(body.postings[0].cost).toEqual(cost);
  expect(body.postings[0].price).toEqual(price);
});
