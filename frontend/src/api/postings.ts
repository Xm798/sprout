import type { Occurrence, Posting, Schedule } from "./types";

export interface FlowLeg {
  posting: Posting;
  /** Effective signed amount; derived for the auto-balance leg. Absent in fallback mode. */
  amount?: number;
  derived: boolean;
}

export interface PostingFlow {
  sources: FlowLeg[];
  destinations: FlowLeg[];
  /** Headline amount (absolute value). Undefined when not computable — callers
   *  fall back to schedule.headline_amount / headline_currency. */
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

  if (legs.length === 0) return fallback();
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

// The multi-posting contract designates two legs by convention: the first
// amount-bearing posting is the "headline" (list/summary display, the leg the
// inbox tunes), and the first blank-amount posting is the auto-balance leg.
// These helpers keep that convention in one place instead of re-deriving it.

/** First amount-bearing leg — the headline used for list/summary display. */
export function headlineLeg(postings?: Posting[]): Posting | undefined {
  return postings?.find((p) => p.amount != null);
}

/** First blank-amount leg — the auto-balance counter-leg. */
export function balanceLeg(postings?: Posting[]): Posting | undefined {
  return postings?.find((p) => p.amount == null);
}

/** Amount to show for an occurrence's headline leg: a per-leg override wins
 *  over the schedule's headline default. Undefined when neither is known. */
export function effectiveHeadlineAmount(
  occurrence: Occurrence,
  schedule?: Schedule
): string | undefined {
  const leg = headlineLeg(schedule?.postings);
  return (
    (leg && occurrence.override_amounts[leg.id]) ??
    schedule?.headline_amount ??
    undefined
  );
}
