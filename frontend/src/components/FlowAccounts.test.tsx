import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { FlowAccounts } from "./FlowAccounts";
import { analyzeFlow } from "../api/postings";
import type { Posting } from "../api/types";

const payroll: Posting[] = [
  { id: "a", account: "Income:Salary", amount: "-10000", currency: "CNY" },
  { id: "b", account: "Expenses:Tax", amount: "1000", currency: "CNY" },
  { id: "c", account: "Expenses:Social", amount: "500", currency: "CNY" },
  { id: "d", account: "Assets:Bank:8888", amount: null, currency: null },
];

const originalMatchMedia = window.matchMedia;
afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

// setup.ts mocks matchMedia with matches:false (mobile). This swaps in a
// wide-viewport version for desktop-cap tests.
function mockWideViewport() {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(min-width: 640px)",
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

test("mobile cap shows 1 account per side and folds the rest into +N", () => {
  render(<FlowAccounts flow={analyzeFlow(payroll)} />);
  expect(screen.getByText("Salary")).toBeInTheDocument();
  expect(screen.getByText("Tax")).toBeInTheDocument();
  const badge = screen.getByText("+2");
  expect(badge).toHaveAttribute("title", "Expenses:Social, Assets:Bank:8888");
  expect(badge.getAttribute("aria-label")).toContain("Expenses:Social");
});

test("wide cap shows 2 accounts per side", () => {
  mockWideViewport();
  render(<FlowAccounts flow={analyzeFlow(payroll)} />);
  expect(screen.getByText("Tax · Social")).toBeInTheDocument();
  expect(screen.getByText("+1")).toBeInTheDocument();
});

test("leafNames=false renders full account paths", () => {
  render(<FlowAccounts flow={analyzeFlow(payroll)} leafNames={false} />);
  expect(screen.getByText("Income:Salary")).toBeInTheDocument();
  expect(screen.getByText("Expenses:Tax")).toBeInTheDocument();
});

test("an empty side renders a dash", () => {
  render(<FlowAccounts flow={analyzeFlow([])} />);
  expect(screen.getAllByText("—").length).toBe(2);
});

test("two-leg flow reads fund account → expense account", () => {
  const flow = analyzeFlow([
    { id: "a", account: "Expenses:Subscription", amount: "15.00", currency: "USD" },
    { id: "b", account: "Assets:CreditCard", amount: null, currency: null },
  ]);
  render(<FlowAccounts flow={flow} />);
  const src = screen.getByText("CreditCard");
  const dst = screen.getByText("Subscription");
  expect(
    src.compareDocumentPosition(dst) & Node.DOCUMENT_POSITION_FOLLOWING
  ).toBeTruthy();
});
