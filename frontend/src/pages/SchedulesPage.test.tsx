import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SchedulesPage } from "./SchedulesPage";
import { makeSchedule, renderWithProviders } from "../test/utils";
import { api } from "../api/client";

const spotify = makeSchedule();

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
