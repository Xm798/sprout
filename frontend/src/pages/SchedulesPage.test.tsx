import { screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { SchedulesPage } from "./SchedulesPage";
import { renderWithProviders } from "../test/utils";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      listSchedules: vi.fn().mockResolvedValue([
        {
          id: 8,
          name: "Payroll",
          narration: "monthly payroll",
          postings: [
            { id: "s1", account: "Income:Salary", amount: "-10000", currency: "CNY" },
            { id: "s2", account: "Expenses:Tax", amount: "1000", currency: "CNY" },
            { id: "s3", account: "Expenses:Social", amount: "500", currency: "CNY" },
            { id: "s4", account: "Assets:Bank:8888", amount: null, currency: null },
          ],
          interval_unit: "month",
          interval_count: 1,
          anchor_date: "2026-01-01",
          tags: "sprout",
          status: "active",
          headline_amount: "-10000",
          headline_currency: "CNY",
          created_at: "2026-01-01T00:00:00",
          updated_at: "2026-01-01T00:00:00",
        },
      ]),
      deleteSchedule: vi.fn(),
    },
  };
});

test("schedule card shows full-path flow, +N badge, and net amount", async () => {
  renderWithProviders(<SchedulesPage />);
  expect(await screen.findByText("Payroll")).toBeInTheDocument();
  expect(screen.getByText("Income:Salary")).toBeInTheDocument(); // full path, not leaf
  expect(screen.getByText("Expenses:Tax")).toBeInTheDocument(); // first destination (mobile cap)
  expect(screen.getByText("+2")).toBeInTheDocument(); // Social + Bank folded
  expect(screen.getByText(/8,500\.00/)).toBeInTheDocument(); // net, not -10000
});
