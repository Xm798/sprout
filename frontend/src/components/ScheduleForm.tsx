import { useState } from "react";
import type { FormEvent } from "react";
import { useAccounts, useCreateSchedule, useCurrencies } from "../api/hooks";
import type { IntervalUnit, ScheduleCreate } from "../api/types";

const EMPTY: ScheduleCreate = {
  name: "",
  narration: "",
  amount: "",
  currency: "USD",
  from_account: "",
  to_account: "",
  interval_unit: "month",
  interval_count: 1,
  anchor_date: "",
  end_date: null,
  max_count: null,
  tags: "sprout",
  status: "active",
};

const UNITS: IntervalUnit[] = ["day", "week", "month", "quarter", "year"];

export function ScheduleForm({ onCreated }: { onCreated?: () => void }) {
  const [form, setForm] = useState<ScheduleCreate>(EMPTY);
  const accounts = useAccounts();
  const currencies = useCurrencies();
  const create = useCreateSchedule();

  function set<K extends keyof ScheduleCreate>(key: K, value: ScheduleCreate[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(form, {
      onSuccess: () => {
        setForm(EMPTY);
        onCreated?.();
      },
    });
  }

  return (
    <form onSubmit={submit} className="space-y-2 rounded border p-3">
      <input
        aria-label="name" required placeholder="Name"
        className="w-full rounded border px-2 py-1"
        value={form.name} onChange={(e) => set("name", e.target.value)}
      />
      <input
        aria-label="amount" required placeholder="Amount"
        className="w-full rounded border px-2 py-1"
        value={form.amount} onChange={(e) => set("amount", e.target.value)}
      />
      <select
        aria-label="currency" className="w-full rounded border px-2 py-1"
        value={form.currency} onChange={(e) => set("currency", e.target.value)}
      >
        {(currencies.data ?? [form.currency]).map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
      <input
        aria-label="from_account" required list="accounts" placeholder="From account"
        className="w-full rounded border px-2 py-1"
        value={form.from_account} onChange={(e) => set("from_account", e.target.value)}
      />
      <input
        aria-label="to_account" required list="accounts" placeholder="To account"
        className="w-full rounded border px-2 py-1"
        value={form.to_account} onChange={(e) => set("to_account", e.target.value)}
      />
      <datalist id="accounts">
        {(accounts.data ?? []).map((a) => (
          <option key={a} value={a} />
        ))}
      </datalist>
      <div className="grid grid-cols-2 gap-2">
        <select
          aria-label="interval_unit" className="rounded border px-2 py-1"
          value={form.interval_unit}
          onChange={(e) => set("interval_unit", e.target.value as IntervalUnit)}
        >
          {UNITS.map((u) => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
        <input
          aria-label="interval_count" type="number" min={1}
          className="rounded border px-2 py-1"
          value={form.interval_count}
          onChange={(e) => set("interval_count", Number(e.target.value))}
        />
      </div>
      <input
        aria-label="anchor_date" type="date" required
        className="w-full rounded border px-2 py-1"
        value={form.anchor_date} onChange={(e) => set("anchor_date", e.target.value)}
      />
      <button
        type="submit" disabled={create.isPending}
        className="rounded bg-green-600 px-3 py-1 text-white disabled:opacity-50"
      >
        {create.isPending ? "Saving…" : "Create schedule"}
      </button>
      {create.isError && (
        <div className="text-sm text-red-600">{String(create.error)}</div>
      )}
    </form>
  );
}
