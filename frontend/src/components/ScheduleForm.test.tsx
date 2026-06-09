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

test("submits a new schedule with the entered values", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ScheduleForm />);

  await user.type(screen.getByLabelText(/^name$/i), "Spotify");
  await user.type(screen.getByLabelText(/^amount$/i), "15.00");
  await user.type(screen.getByLabelText(/from account/i), "Assets:CreditCard");
  await user.type(screen.getByLabelText(/to account/i), "Expenses:Subscription");
  await user.type(screen.getByLabelText(/starting from/i), "2026-01-15");
  await user.click(screen.getByRole("button", { name: /create schedule/i }));

  await waitFor(() => expect(api.createSchedule).toHaveBeenCalledTimes(1));
  const arg = (api.createSchedule as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg).toMatchObject({
    name: "Spotify",
    amount: "15.00",
    from_account: "Assets:CreditCard",
    to_account: "Expenses:Subscription",
    anchor_date: "2026-01-15",
    interval_unit: "month",
    interval_count: 1,
  });
});
