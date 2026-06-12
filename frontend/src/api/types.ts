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

export interface Posting {
  id: string; // client-generated UUID, unique within a schedule
  account: string;
  amount?: string | null; // null/absent = auto-balance leg
  currency?: string | null; // required when amount is present
  cost?: Cost | null;
  price?: Price | null;
}

export interface ScheduleCreate {
  name: string;
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

export interface Schedule extends ScheduleCreate {
  id: number;
  headline_amount?: string | null; // first amount-bearing leg, for list/summary views
  headline_currency?: string | null;
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
  lookahead_days: number;
}
