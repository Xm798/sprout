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
    parseTransaction: vi.fn(),
    getExchangeRate: vi.fn(),
  },
}));

const PARSED = {
  payee: "Spotify",
  narration: "sub",
  tags: "music,sprout",
  anchor_date: "2026-06-15",
  postings: [
    { id: "x", account: "Expenses:Subscription", amount: "15.00", currency: "USD", cost: null, price: null },
    { id: "y", account: "Assets:CreditCard", amount: null, currency: null, cost: null, price: null },
  ],
  warnings: [] as string[],
};

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

test("fixed schedule payload includes kind='fixed'", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "Rent");
  await user.type(screen.getByLabelText(/account 1/i), "Expenses:Rent");
  await user.type(screen.getByLabelText(/amount 1/i), "1200.00");
  await user.type(screen.getByLabelText(/account 2/i), "Assets:Checking");
  await user.click(screen.getByLabelText(/starting from/i));
  await user.click(await screen.findByRole("button", { name: /today/i }));

  await user.click(screen.getByRole("button", { name: /create schedule/i }));

  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg.kind).toBe("fixed");
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


// ── Per-posting exchange rate ────────────────────────────────────────────────

test("fetches an exchange rate into a posting's price on demand", async () => {
  const user = userEvent.setup();
  vi.mocked(api.getExchangeRate).mockResolvedValue({
    base: "USD", quote: "CNY", rate: "7.1234",
    source: "frankfurter", as_of: "2026-06-25", cached: false,
  });
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/amount 1/i), "100");
  // Price controls are hidden until the user reveals them per leg.
  expect(screen.queryByLabelText(/price 1/i)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /exchange rate/i }));

  await user.type(screen.getByLabelText(/price currency 1/i), "CNY");
  await user.click(screen.getByRole("button", { name: /fetch rate/i }));

  await waitFor(() =>
    expect(screen.getByLabelText(/price 1/i)).toHaveValue("7.1234")
  );
  expect(api.getExchangeRate).toHaveBeenCalledWith("USD", "CNY");
  // The provider + effective date are surfaced so the user trusts the number.
  expect(screen.getByText(/frankfurter/i)).toBeInTheDocument();
  expect(screen.getByText(/2026-06-25/)).toBeInTheDocument();
});

test("submits the fetched price on the posting and drops an empty one", async () => {
  const user = userEvent.setup();
  vi.mocked(api.getExchangeRate).mockResolvedValue({
    base: "USD", quote: "CNY", rate: "7.1234",
    source: "frankfurter", as_of: "2026-06-25", cached: false,
  });
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "FX");
  await user.type(screen.getByLabelText(/account 1/i), "Expenses:Subscription");
  await user.type(screen.getByLabelText(/amount 1/i), "100");
  await user.type(screen.getByLabelText(/account 2/i), "Assets:CreditCard");
  await user.click(screen.getByLabelText(/starting from/i));
  await user.click(await screen.findByRole("button", { name: /today/i }));

  await user.click(screen.getByRole("button", { name: /exchange rate/i }));
  await user.type(screen.getByLabelText(/price currency 1/i), "CNY");
  await user.click(screen.getByRole("button", { name: /fetch rate/i }));
  await waitFor(() =>
    expect(screen.getByLabelText(/price 1/i)).toHaveValue("7.1234")
  );

  await user.click(screen.getByRole("button", { name: /create schedule/i }));
  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg.postings[0].price).toEqual({
    amount: "7.1234", currency: "CNY", total: false,
  });
  // Leg 2 (auto-balance) carries no price.
  expect(arg.postings[1].price).toBeUndefined();
});

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/^name$/i), "FX");
  await user.type(screen.getByLabelText(/account 1/i), "Expenses:Subscription");
  await user.type(screen.getByLabelText(/amount 1/i), "100");
  await user.type(screen.getByLabelText(/account 2/i), "Assets:CreditCard");
  await user.click(screen.getByLabelText(/starting from/i));
  await user.click(await screen.findByRole("button", { name: /today/i }));
}

test("blocks submit when a price row has a rate but no currency", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);
  await fillRequired(user);

  await user.click(screen.getByRole("button", { name: /exchange rate/i }));
  await user.type(screen.getByLabelText(/price 1/i), "0.86"); // amount only

  await user.click(screen.getByRole("button", { name: /create schedule/i }));
  expect(await screen.findByText(/rate and its currency/i)).toBeInTheDocument();
  expect(api.createSchedule).not.toHaveBeenCalled();
});

test("blocks submit when a price amount is not a number", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);
  await fillRequired(user);

  await user.click(screen.getByRole("button", { name: /exchange rate/i }));
  await user.type(screen.getByLabelText(/price currency 1/i), "CNY");
  await user.type(screen.getByLabelText(/price 1/i), "abc");

  await user.click(screen.getByRole("button", { name: /create schedule/i }));
  expect(await screen.findByText(/must be a number/i)).toBeInTheDocument();
  expect(api.createSchedule).not.toHaveBeenCalled();
});

test("an opened but empty price row is dropped and does not block submit", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);
  await fillRequired(user);

  // Reveal the price row but leave it empty.
  await user.click(screen.getByRole("button", { name: /exchange rate/i }));
  await user.click(screen.getByRole("button", { name: /create schedule/i }));

  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg.postings[0].price).toBeNull();
});

// ── Import from bean text ────────────────────────────────────────────────────

async function openImportAndParse(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /import from bean text/i }));
  await user.type(screen.getByLabelText(/bean text/i), "x");
  await user.click(screen.getByRole("button", { name: /parse & fill/i }));
}

test("import fills the form from parsed bean text on a clean form, no confirm", async () => {
  const user = userEvent.setup();
  vi.mocked(api.parseTransaction).mockResolvedValue({ ...PARSED });
  const confirmSpy = vi.spyOn(window, "confirm");
  renderWithProviders(<ScheduleForm />);

  await openImportAndParse(user);

  await waitFor(() => expect(screen.getByLabelText(/^narration$/i)).toHaveValue("sub"));
  expect(screen.getByLabelText(/^payee$/i)).toHaveValue("Spotify");
  expect(screen.getByLabelText(/amount 1/i)).toHaveValue("15.00");
  expect(screen.getByLabelText(/account 2/i)).toHaveValue("Assets:CreditCard");
  // name is the schedule's own label — never overwritten by import
  expect(screen.getByLabelText(/^name$/i)).toHaveValue("");
  // recurrence fields are left untouched at their defaults
  expect(screen.getByLabelText(/repeat count/i)).toHaveValue(1);
  expect(confirmSpy).not.toHaveBeenCalled();
  confirmSpy.mockRestore();
});

test("import confirms before overwriting a dirty form and respects cancel", async () => {
  const user = userEvent.setup();
  vi.mocked(api.parseTransaction).mockResolvedValue({ ...PARSED });
  const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "Manual");
  await openImportAndParse(user);

  await waitFor(() => expect(confirmSpy).toHaveBeenCalledTimes(1));
  // cancelled -> nothing overwritten
  expect(screen.getByLabelText(/^name$/i)).toHaveValue("Manual");
  confirmSpy.mockRestore();
});

test("import surfaces structural warnings returned by the backend", async () => {
  const user = userEvent.setup();
  vi.mocked(api.parseTransaction).mockResolvedValue({
    ...PARSED,
    warnings: ["a transaction needs at least 2 postings"],
  });
  renderWithProviders(<ScheduleForm />);

  await openImportAndParse(user);

  expect(
    await screen.findByText(/a transaction needs at least 2 postings/i)
  ).toBeInTheDocument();
});

test("import shows a friendly message when parsing fails", async () => {
  const user = userEvent.setup();
  vi.mocked(api.parseTransaction).mockRejectedValue(new Error("no transaction found"));
  renderWithProviders(<ScheduleForm />);

  await openImportAndParse(user);

  expect(
    await screen.findByText(/no transaction found in the text/i)
  ).toBeInTheDocument();
  // form is left untouched on error
  expect(screen.getByLabelText(/^name$/i)).toHaveValue("");
});

test("import section is hidden in edit mode", () => {
  renderWithProviders(<ScheduleForm schedule={makeSchedule()} />);
  expect(
    screen.queryByRole("button", { name: /import from bean text/i })
  ).not.toBeInTheDocument();
});

// ── Loan type selector ───────────────────────────────────────────────────────

test("selecting a loan type reveals loan fields and hides postings/end-date/max-count", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  // Fixed by default: postings, end date, max count visible; loan fields not.
  expect(screen.getByLabelText(/account 1/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/end date/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/max occurrences/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/^principal$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/annual rate/i)).not.toBeInTheDocument();

  // Switch to equal_payment.
  await user.click(screen.getByRole("combobox", { name: /type/i }));
  await user.click(await screen.findByRole("option", { name: /equal payment/i }));

  // Loan fields are now visible.
  expect(screen.getByLabelText(/^principal$/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/annual rate/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/term \(months\)/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/principal account/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/interest account/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/payment account/i)).toBeInTheDocument();
  // Postings, end date, max count are hidden.
  expect(screen.queryByLabelText(/account 1/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/end date/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/max occurrences/i)).not.toBeInTheDocument();
});

test("loan equal_payment submit produces kind=loan with decimal annual_rate and role postings", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "Home Loan");

  await user.click(screen.getByRole("combobox", { name: /type/i }));
  await user.click(await screen.findByRole("option", { name: /equal payment/i }));

  await user.type(screen.getByLabelText(/^principal$/i), "1000000");
  await user.type(screen.getByLabelText(/annual rate/i), "4.85");
  await user.type(screen.getByLabelText(/term \(months\)/i), "240");
  await user.type(screen.getByLabelText(/principal account/i), "Liabilities:Mortgage");
  await user.type(screen.getByLabelText(/interest account/i), "Expenses:Interest");
  await user.type(screen.getByLabelText(/payment account/i), "Assets:Checking");
  await user.click(screen.getByLabelText(/starting from/i));
  await user.click(await screen.findByRole("button", { name: /today/i }));

  await user.click(screen.getByRole("button", { name: /create schedule/i }));

  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];

  expect(arg.kind).toBe("loan");
  expect(arg.loan).toEqual({
    principal: "1000000",
    annual_rate: "0.0485",
    term_count: 240,
    method: "equal_payment",
  });
  expect(arg.postings).toHaveLength(3);
  expect(arg.postings[0]).toMatchObject({ account: "Liabilities:Mortgage", role: "principal", currency: "USD" });
  expect(arg.postings[1]).toMatchObject({ account: "Expenses:Interest", role: "interest", currency: "USD" });
  expect(arg.postings[2]).toMatchObject({ account: "Assets:Checking", role: "payment", currency: "USD" });
  // Loan schedules have no terminal conditions.
  expect(arg.end_date).toBeNull();
  expect(arg.max_count).toBeNull();
});

test("loan equal_principal submit uses correct method", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "Car Loan");

  await user.click(screen.getByRole("combobox", { name: /type/i }));
  await user.click(await screen.findByRole("option", { name: /equal principal/i }));

  await user.type(screen.getByLabelText(/^principal$/i), "50000");
  await user.type(screen.getByLabelText(/annual rate/i), "3.6");
  await user.type(screen.getByLabelText(/term \(months\)/i), "60");
  await user.type(screen.getByLabelText(/principal account/i), "Liabilities:CarLoan");
  await user.type(screen.getByLabelText(/interest account/i), "Expenses:Interest");
  await user.type(screen.getByLabelText(/payment account/i), "Assets:Checking");
  await user.click(screen.getByLabelText(/starting from/i));
  await user.click(await screen.findByRole("button", { name: /today/i }));

  await user.click(screen.getByRole("button", { name: /create schedule/i }));

  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];

  expect(arg.loan.method).toBe("equal_principal");
  expect(arg.loan.annual_rate).toBe("0.036");
  expect(arg.loan.term_count).toBe(60);
});
