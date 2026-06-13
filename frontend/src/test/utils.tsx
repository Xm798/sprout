import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { Schedule } from "../api/types";

// Canonical two-leg schedule for tests; override fields via the argument.
// Mirrors new_schedule_payload() in backend/tests/conftest.py.
export function makeSchedule(overrides: Partial<Schedule> = {}): Schedule {
  return {
    id: 7,
    name: "Spotify",
    narration: "sub",
    interval_unit: "month",
    interval_count: 1,
    anchor_date: "2026-01-15",
    end_date: null,
    max_count: 6,
    tags: "sprout",
    status: "active",
    target_file: null,
    postings: [
      { id: "main", account: "Expenses:Subscription", amount: "15.00", currency: "USD" },
      { id: "bal", account: "Assets:CreditCard", amount: null, currency: null },
    ],
    headline_amount: "15.00",
    headline_currency: "USD",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    ...overrides,
  };
}

export function renderWithProviders(ui: ReactElement, route = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}
