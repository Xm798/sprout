export type IntervalUnit = "day" | "week" | "month" | "quarter" | "year";

export interface Cost {
  amount: string; // decimal serialized as string
  currency: string;
  total: boolean; // true -> {{...}} total cost; false -> {...} per-unit
}

export interface Price {
  amount: string; // decimal serialized as string
  currency: string;
  total: boolean; // true -> @@ total price; false -> @ per-unit
}

export interface RateQuote {
  base: string;
  quote: string;
  rate: string; // decimal serialized as string
  source: string; // "frankfurter" | "coingecko"
  as_of: string; // YYYY-MM-DD the rate is effective for
  cached: boolean;
}

export type LoanMethod = "equal_payment" | "equal_principal";

export interface LoanData {
  principal: string; // decimal serialized as string
  annual_rate: string; // decimal (not percent), e.g. "0.0485" for 4.85%
  term_count: number;
  method: LoanMethod;
}

// A prepayment or rate-change event attached to a loan. Amounts/rates are
// decimal strings on the wire, mirroring LoanData.annual_rate.
export type PrepaymentMode = "shorten_term" | "reduce_payment";

export interface AmortizationEvent {
  id?: string; // uuid-hex string assigned by the backend
  kind: "prepayment" | "rate_change";
  date: string; // YYYY-MM-DD — must fall on a payment date
  amount?: string | null; // prepayment only
  mode?: PrepaymentMode | null; // prepayment only
  annual_rate?: string | null; // rate_change only, decimal (not percent)
}

// POST body for creating an event on a saved schedule.
export type ScheduleEventBody =
  | { kind: "prepayment"; date: string; amount: string; mode: PrepaymentMode }
  | { kind: "rate_change"; date: string; annual_rate: string };

export interface AmortizationPreviewBody {
  loan: LoanData;
  anchor_date: string; // YYYY-MM-DD
  interval_count: number;
  events: AmortizationEvent[];
}

export interface AmortizationRow {
  seq: number | null; // null for prepayment rows
  due_date: string;
  principal: string; // decimal serialized as string
  interest: string;
  payment: string;
  balance_after: string;
  is_prepayment: boolean;
  event_id?: string | null; // uuid-hex string; only set on prepayment rows
}

export interface AmortizationResult {
  rows: AmortizationRow[];
  total_interest: string;
  payoff_date: string;
}

export interface Posting {
  id: string; // client-generated UUID, unique within a schedule
  account: string;
  amount?: string | null; // null/absent = auto-balance leg
  currency?: string | null; // required when amount is present
  cost?: Cost | null;
  price?: Price | null;
  role?: "principal" | "interest" | "payment"; // loan leg role
}

export interface ScheduleCreate {
  kind?: "fixed" | "loan";
  loan?: LoanData | null;
  name: string; // Sprout-internal label; never written to the ledger
  payee: string; // bean payee
  narration: string;
  postings: Posting[];
  interval_unit: IntervalUnit;
  interval_count: number;
  anchor_date: string; // YYYY-MM-DD
  end_date?: string | null;
  max_count?: number | null;
  tags: string;
  status: string; // active | paused
  target_file?: string | null; // relative .bean path; null = global write strategy
}

export interface ParseBeanRequest {
  text: string;
}

// Transaction-level fields parsed from pasted bean text; recurrence fields are
// filled in by the user. anchor_date is the wire format (ISO date string).
// No `name`: the schedule name is internal to Sprout and never parsed from bean.
export interface ParsedTransaction {
  payee: string;
  narration: string;
  postings: Posting[];
  tags: string;
  anchor_date: string;
  warnings: string[];
}

export interface Schedule extends ScheduleCreate {
  id: number;
  headline_amount?: string | null; // first amount-bearing leg; display fallback when analyzeFlow can't compute
  headline_currency?: string | null;
  events?: AmortizationEvent[]; // loan prepayment / rate-change events, if any
  created_at: string;
  updated_at: string;
}

export interface Occurrence {
  id: number;
  schedule_id: number;
  due_date: string;
  status: "pending" | "confirmed" | "skipped";
  override_amounts: Record<string, string>; // posting id -> amount; always present, may be empty
  override_date?: string | null;
  override_narration?: string | null;
  written_path?: string | null;
  sprout_id?: string | null;
  confirmed_at?: string | null;
  // Loan-schedule provenance. Regular (non-loan) rows use the backend
  // sentinels: loan_event "regular" and event_id "" (never null); loan_seq is
  // the 1-based installment index and is null on rows that aren't a scheduled
  // installment. All three are read-only, echoed straight from the server.
  loan_seq?: number | null;
  loan_event?: string;
  event_id?: string;
}

export interface HistoryCheck {
  missing: number[]; // ids of confirmed occurrences absent from the ledger
}

export interface WrittenTransaction {
  path: string; // file the block currently lives in (loader-reported)
  text: string; // the exact block, including any manual edits
}

export interface ConfirmBody {
  override_amounts?: Record<string, string>;
  override_date?: string | null;
  override_narration?: string | null;
}

export type PreviewBody = ConfirmBody;

export interface AppConfig {
  id: number;
  ledger_main_file: string;
  ledger_root: string;
  write_mode: string; // single_file | month_file
  single_file_name: string;
  month_file_template: string;
  default_tag: string;
  default_currency: string;
  lookahead_days: number;
}
