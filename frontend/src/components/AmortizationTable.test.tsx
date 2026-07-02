import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { AmortizationTable } from "./AmortizationTable";
import { renderWithProviders } from "../test/utils";
import { api } from "../api/client";
import type { AmortizationResult, LoanData } from "../api/types";
import { formatDate } from "../lib/utils";

vi.mock("../api/client", () => ({
  api: {
    previewAmortization: vi.fn(),
    addScheduleEvent: vi.fn(),
    deleteScheduleEvent: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const LOAN: LoanData = {
  principal: "100000",
  annual_rate: "0.0485",
  term_count: 3,
  method: "equal_payment",
};

const PREVIEW: AmortizationResult = {
  rows: [
    {
      seq: 1,
      due_date: "2026-02-15",
      principal: "33000.00",
      interest: "404.17",
      payment: "33404.17",
      balance_after: "67000.00",
      is_prepayment: false,
    },
    {
      seq: 2,
      due_date: "2026-03-15",
      principal: "33500.00",
      interest: "270.79",
      payment: "33770.79",
      balance_after: "33500.00",
      is_prepayment: false,
    },
    {
      seq: 3,
      due_date: "2026-04-15",
      principal: "33500.00",
      interest: "135.40",
      payment: "33635.40",
      balance_after: "0.00",
      is_prepayment: false,
    },
  ],
  total_interest: "810.36",
  payoff_date: "2026-04-15",
};

afterEach(() => vi.clearAllMocks());

const previewMock = api.previewAmortization as ReturnType<typeof vi.fn>;
const addMock = api.addScheduleEvent as ReturnType<typeof vi.fn>;

test("renders schedule rows plus the total interest and payoff date", async () => {
  previewMock.mockResolvedValue(PREVIEW);
  renderWithProviders(
    <AmortizationTable
      loan={LOAN}
      anchorDate="2026-01-15"
      intervalCount={1}
      currency="USD"
    />
  );

  // A row for each installment (matched by its due date cell).
  expect(await screen.findByText("2026-02-15")).toBeInTheDocument();
  expect(screen.getByText("2026-03-15")).toBeInTheDocument();
  expect(screen.getByText("2026-04-15")).toBeInTheDocument();

  // Summary: total interest (money-formatted with currency) and payoff date.
  expect(screen.getByText(/810\.36 USD/)).toBeInTheDocument();
  expect(screen.getByText(formatDate("2026-04-15"))).toBeInTheDocument();

  // The request carried the decimal loan params and an empty events list.
  const body = previewMock.mock.calls[0][0];
  expect(body).toMatchObject({
    loan: LOAN,
    anchor_date: "2026-01-15",
    interval_count: 1,
    events: [],
  });
});

test("prepayment action posts the correct body to the events endpoint", async () => {
  previewMock.mockResolvedValue(PREVIEW);
  addMock.mockResolvedValue({ id: 7, events: [] });
  const user = userEvent.setup();

  renderWithProviders(
    <AmortizationTable
      loan={LOAN}
      anchorDate="2026-01-15"
      intervalCount={1}
      currency="USD"
      scheduleId={7}
    />
  );

  // Event actions appear once the preview (with its payment dates) resolves.
  const amount = await screen.findByLabelText(/prepayment amount/i);
  await user.type(amount, "50000");
  await user.click(screen.getByRole("button", { name: /apply/i }));

  await waitFor(() => expect(addMock).toHaveBeenCalledTimes(1));
  expect(addMock.mock.calls[0]).toEqual([
    7,
    {
      kind: "prepayment",
      date: "2026-02-15", // defaults to the first previewed payment date
      amount: "50000",
      mode: "shorten_term",
    },
  ]);
});

test("surfaces the 422 boundary error from the events endpoint", async () => {
  const { toast } = await import("sonner");
  previewMock.mockResolvedValue(PREVIEW);
  addMock.mockRejectedValue(
    new Error("event date must be a payment date after the last confirmed installment")
  );
  const user = userEvent.setup();

  renderWithProviders(
    <AmortizationTable
      loan={LOAN}
      anchorDate="2026-01-15"
      intervalCount={1}
      currency="USD"
      scheduleId={7}
    />
  );

  await user.type(await screen.findByLabelText(/prepayment amount/i), "50000");
  await user.click(screen.getByRole("button", { name: /apply/i }));

  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        description: expect.stringContaining("payment date"),
      })
    )
  );
});
