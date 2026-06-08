import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useConfig, useUpdateConfig } from "../api/hooks";
import type { AppConfig } from "../api/types";

export function SettingsPage() {
  const config = useConfig();
  const update = useUpdateConfig();
  const [form, setForm] = useState<AppConfig | null>(null);

  useEffect(() => {
    if (config.data) setForm(config.data);
  }, [config.data]);

  if (!form) return <div className="p-4">Loading…</div>;

  function set<K extends keyof AppConfig>(key: K, value: AppConfig[K]) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (form) update.mutate(form);
  }

  return (
    <form onSubmit={submit} className="max-w-xl space-y-3 p-4">
      <h1 className="text-xl font-semibold">Settings</h1>

      <label className="block text-sm">
        Ledger main file
        <input
          className="w-full rounded border px-2 py-1"
          value={form.ledger_main_file}
          onChange={(e) => set("ledger_main_file", e.target.value)}
        />
      </label>

      <label className="block text-sm">
        Ledger root
        <input
          className="w-full rounded border px-2 py-1"
          value={form.ledger_root}
          onChange={(e) => set("ledger_root", e.target.value)}
        />
      </label>

      <label className="block text-sm">
        Write mode
        <select
          className="w-full rounded border px-2 py-1"
          value={form.write_mode}
          onChange={(e) => set("write_mode", e.target.value)}
        >
          <option value="single_file">single_file</option>
          <option value="month_file">month_file</option>
        </select>
      </label>

      <label className="block text-sm">
        Month file template
        <input
          className="w-full rounded border px-2 py-1"
          value={form.month_file_template}
          onChange={(e) => set("month_file_template", e.target.value)}
        />
      </label>

      <label className="block text-sm">
        Default tag
        <input
          className="w-full rounded border px-2 py-1"
          value={form.default_tag}
          onChange={(e) => set("default_tag", e.target.value)}
        />
      </label>

      <label className="block text-sm">
        Lookahead days
        <input
          type="number"
          className="w-full rounded border px-2 py-1"
          value={form.lookahead_days}
          onChange={(e) => set("lookahead_days", Number(e.target.value))}
        />
      </label>

      <button
        type="submit"
        disabled={update.isPending}
        className="rounded bg-green-600 px-3 py-1 text-white disabled:opacity-50"
      >
        Save
      </button>
      {update.isSuccess && (
        <span className="ml-2 text-sm text-green-700">Saved</span>
      )}
    </form>
  );
}
