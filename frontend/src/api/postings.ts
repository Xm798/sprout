import type { Occurrence, Posting, Schedule } from "./types";

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
