import type { Posting, Schedule } from "./types";

export interface FlowLeg {
  posting: Posting;
  /** Effective signed amount; derived for the auto-balance leg. Absent in fallback mode. */
  amount?: number;
  derived: boolean;
}

export interface PostingFlow {
  sources: FlowLeg[];
  destinations: FlowLeg[];
  /** Headline amount (absolute value). Undefined when not computable —
   *  headlineDisplay() resolves the schedule fallback for display. */
  amount?: string;
  currency?: string;
}

/** Strip float-sum noise (0.1 + 0.2) without introducing trailing zeros. */
function clean(n: number): number {
  return Number(n.toFixed(6));
}

/**
 * Group legs by money flow (negative → sources, ≥0 → destinations) and compute
 * the headline amount: net change of the auto-balance leg, or the gross
 * positive sum when every leg is explicit. Overrides act on effective amounts,
 * so an override may fill the blank leg (then the all-explicit branch applies).
 * Falls back to legacy first-amount-leg → first-blank-leg grouping when the
 * flow isn't computable (≥2 blank legs, unparseable, mixed currencies,
 * cost/price present).
 */
export function analyzeFlow(
  postings?: Posting[],
  overrides?: Record<string, string>
): PostingFlow {
  const legs = postings ?? [];

  function fallback(): PostingFlow {
    const head = legs.find((p) => p.amount != null);
    const blank = legs.find((p) => p.amount == null);
    const right = blank ? [blank] : legs.filter((p) => p !== head);
    const wrap = (posting: Posting): FlowLeg => ({ posting, derived: false });
    return {
      sources: head ? [wrap(head)] : [],
      destinations: right.map(wrap),
    };
  }

  if (legs.some((p) => p.cost != null || p.price != null)) return fallback();

  const raws = legs.map((posting) => ({
    posting,
    raw: overrides?.[posting.id] ?? posting.amount,
  }));
  const blanks = raws.filter((r) => r.raw == null);
  if (blanks.length > 1 || blanks.length === legs.length) return fallback();

  const explicit = raws.filter((r) => r.raw != null);
  // An override-filled blank leg has no currency of its own; assume the shared one.
  const currencies = new Set(
    explicit.map((r) => r.posting.currency).filter((c): c is string => c != null)
  );
  if (currencies.size !== 1) return fallback();

  const values = explicit.map((r) => Number(r.raw));
  if (values.some(Number.isNaN)) return fallback();
  const sum = clean(values.reduce((a, b) => a + b, 0));

  const flowLegs: FlowLeg[] = raws.map((r) =>
    r.raw == null
      ? { posting: r.posting, amount: clean(-sum), derived: true }
      : { posting: r.posting, amount: clean(Number(r.raw)), derived: false }
  );

  const headline =
    blanks.length === 1
      ? Math.abs(sum)
      : flowLegs.reduce((a, l) => (l.amount! > 0 ? a + l.amount! : a), 0);

  return {
    sources: flowLegs.filter((l) => l.amount! < 0),
    destinations: flowLegs.filter((l) => l.amount! >= 0),
    amount: String(clean(headline)),
    currency: [...currencies][0],
  };
}

/** Display amount/currency for a flow: the computed net, or the schedule's
 *  backend headline when the flow isn't computable. Undefined when neither
 *  source knows. */
export function headlineDisplay(
  flow: PostingFlow,
  schedule?: Schedule
): { amount?: string; currency?: string } {
  return {
    amount: flow.amount ?? schedule?.headline_amount ?? undefined,
    currency: flow.currency ?? schedule?.headline_currency ?? undefined,
  };
}

// Posting helpers. analyzeFlow() is the single source of truth for list/summary
// display: flow grouping and the net headline amount. headlineLeg() remains the
// convention for which leg the inbox amount editor tunes (first amount-bearing).

/** First amount-bearing leg — the editable leg that the inbox amount editor tunes. */
export function headlineLeg(postings?: Posting[]): Posting | undefined {
  return postings?.find((p) => p.amount != null);
}
