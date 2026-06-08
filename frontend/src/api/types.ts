export type IntervalUnit = "day" | "week" | "month" | "quarter" | "year";

export interface ScheduleCreate {
  name: string;
  narration: string;
  amount: string; // decimal serialized as string
  currency: string;
  from_account: string;
  to_account: string;
  interval_unit: IntervalUnit;
  interval_count: number;
  anchor_date: string; // YYYY-MM-DD
  end_date?: string | null;
  max_count?: number | null;
  tags: string;
  status: string; // active | paused
}

export interface Schedule extends ScheduleCreate {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface Occurrence {
  id: number;
  schedule_id: number;
  due_date: string;
  status: "pending" | "confirmed" | "skipped";
  override_amount?: string | null;
  override_date?: string | null;
  override_narration?: string | null;
  written_path?: string | null;
  sprout_id?: string | null;
  confirmed_at?: string | null;
}

export interface ConfirmBody {
  override_amount?: string | null;
  override_date?: string | null;
  override_narration?: string | null;
}

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
