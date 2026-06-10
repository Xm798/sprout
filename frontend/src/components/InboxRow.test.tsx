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
  },
}));

afterEach(() => vi.clearAllMocks());

const occurrence: Occurrence = {
  id: 1, schedule_id: 7, due_date: "2026-06-15", status: "pending",
  override_amounts: {}, override_date: null, override_narration: null,
  written_path: null, sprout_id: "sch7-20260615", confirmed_at: null,
};

const schedule: Schedule = {
  id: 7, name: "Spotify", narration: "sub",
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

test("editing the amount sends override_amounts keyed by the headline posting id", async () => {
  const user = userEvent.setup();
  renderWithProviders(<InboxRow occurrence={occurrence} schedule={schedule} />);
  await user.click(screen.getByRole("button", { name: /preview/i }));
  await user.type(screen.getByLabelText(/^amount/i), "20.00");
  await user.click(screen.getByRole("button", { name: /^confirm$/i }));
  await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
  expect(api.confirm).toHaveBeenCalledWith(1, {
    override_amounts: { p1: "20.00" },
  });
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
