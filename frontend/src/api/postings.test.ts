import { describe, expect, test } from "vitest";
import { analyzeFlow } from "./postings";
import type { Posting } from "./types";

const p = (
  id: string,
  account: string,
  amount: string | null,
  currency: string | null = amount != null ? "CNY" : null
): Posting => ({ id, account, amount, currency });

const accounts = (legs: { posting: Posting }[]) =>
  legs.map((l) => l.posting.account);

describe("analyzeFlow", () => {
  test("two-leg baseline: blank fund leg becomes the source, amount = net change", () => {
    const flow = analyzeFlow([
      p("a", "Expenses:Food", "80"),
      p("b", "Assets:Bank:3577", null),
    ]);
    expect(accounts(flow.sources)).toEqual(["Assets:Bank:3577"]);
    expect(accounts(flow.destinations)).toEqual(["Expenses:Food"]);
    expect(flow.sources[0].derived).toBe(true);
    expect(flow.amount).toBe("80");
    expect(flow.currency).toBe("CNY");
  });

  test("one source, many destinations (split expense)", () => {
    const flow = analyzeFlow([
      p("a", "Expenses:Food", "80"),
      p("b", "Expenses:Fee", "20"),
      p("c", "Assets:Bank:3577", null),
    ]);
    expect(accounts(flow.sources)).toEqual(["Assets:Bank:3577"]);
    expect(accounts(flow.destinations)).toEqual(["Expenses:Food", "Expenses:Fee"]);
    expect(flow.amount).toBe("100");
  });

  test("payroll: derived bank leg lands in destinations, amount = net to bank", () => {
    const flow = analyzeFlow([
      p("a", "Income:Salary", "-10000"),
      p("b", "Expenses:Tax", "1000"),
      p("c", "Expenses:Social", "500"),
      p("d", "Assets:Bank:8888", null),
    ]);
    expect(accounts(flow.sources)).toEqual(["Income:Salary"]);
    expect(accounts(flow.destinations)).toEqual([
      "Expenses:Tax",
      "Expenses:Social",
      "Assets:Bank:8888",
    ]);
    expect(flow.destinations[2].derived).toBe(true);
    expect(flow.destinations[2].amount).toBe(8500);
    expect(flow.amount).toBe("8500");
  });

  test("many-to-many with all-explicit amounts: amount = sum of positive legs", () => {
    const flow = analyzeFlow([
      p("a", "Assets:Bank:3577", "-60"),
      p("b", "Assets:Bank:6688", "-40"),
      p("c", "Expenses:Food", "80"),
      p("d", "Expenses:Fee", "20"),
    ]);
    expect(accounts(flow.sources)).toEqual(["Assets:Bank:3577", "Assets:Bank:6688"]);
    expect(accounts(flow.destinations)).toEqual(["Expenses:Food", "Expenses:Fee"]);
    expect(flow.amount).toBe("100");
  });

  test("override changes the derived amount", () => {
    const flow = analyzeFlow(
      [p("a", "Expenses:Food", "80"), p("b", "Expenses:Fee", "20"), p("c", "Assets:Bank:3577", null)],
      { a: "90" }
    );
    expect(flow.amount).toBe("110");
  });

  test("override filling the only blank leg routes to the all-explicit branch", () => {
    const flow = analyzeFlow(
      [p("a", "Expenses:Food", "80"), p("b", "Assets:Bank:3577", null)],
      { b: "-80" }
    );
    expect(accounts(flow.sources)).toEqual(["Assets:Bank:3577"]);
    expect(flow.sources[0].derived).toBe(false);
    expect(flow.amount).toBe("80");
  });

  test("float noise is normalized away", () => {
    const flow = analyzeFlow([
      p("a", "Expenses:Food", "0.1"),
      p("b", "Expenses:Fee", "0.2"),
      p("c", "Assets:Bank:3577", null),
    ]);
    expect(flow.amount).toBe("0.3");
  });

  test("zero-amount legs land in destinations", () => {
    const flow = analyzeFlow([
      p("a", "Assets:A", "-10"),
      p("b", "Expenses:B", "0"),
      p("c", "Assets:C", null),
    ]);
    expect(accounts(flow.destinations)).toEqual(["Expenses:B", "Assets:C"]);
    expect(flow.amount).toBe("10");
  });

  // Fallback cases: amount undefined, legacy grouping (first amount leg → first
  // blank leg, or all remaining legs when no blank).
  test("mixed currencies fall back", () => {
    const flow = analyzeFlow([
      p("a", "Expenses:Food", "80", "CNY"),
      p("b", "Expenses:Fee", "5", "USD"),
      p("c", "Assets:Bank:3577", null),
    ]);
    expect(flow.amount).toBeUndefined();
    expect(flow.currency).toBeUndefined();
    expect(accounts(flow.sources)).toEqual(["Expenses:Food"]);
    expect(accounts(flow.destinations)).toEqual(["Assets:Bank:3577"]);
  });

  test("cost or price on any leg falls back", () => {
    const legs: Posting[] = [
      { ...p("a", "Assets:Broker", "1"), cost: { amount: "100", currency: "USD", total: false } },
      p("b", "Assets:Bank:3577", null),
    ];
    expect(analyzeFlow(legs).amount).toBeUndefined();
  });

  test("two blank legs fall back", () => {
    const flow = analyzeFlow([
      p("a", "Expenses:Food", "80"),
      p("b", "Assets:A", null),
      p("c", "Assets:B", null),
    ]);
    expect(flow.amount).toBeUndefined();
    expect(accounts(flow.destinations)).toEqual(["Assets:A"]);
  });

  test("unparseable amount falls back", () => {
    expect(
      analyzeFlow([p("a", "Expenses:Food", "abc"), p("b", "Assets:Bank:3577", null)]).amount
    ).toBeUndefined();
  });

  test("empty / undefined postings fall back safely", () => {
    expect(analyzeFlow(undefined).amount).toBeUndefined();
    expect(analyzeFlow([]).sources).toEqual([]);
  });
});
