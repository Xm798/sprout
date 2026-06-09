import { useState } from "react";
import type { FormEvent } from "react";

import { useAccounts, useCreateSchedule, useCurrencies } from "@/api/hooks";
import type { IntervalUnit, ScheduleCreate } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

  function set<K extends keyof ScheduleCreate>(
    key: K,
    value: ScheduleCreate[K]
  ) {
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
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="sf-name">Name</Label>
        <Input
          id="sf-name"
          required
          placeholder="e.g. Netflix"
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2 space-y-1.5">
          <Label htmlFor="sf-amount">Amount</Label>
          <Input
            id="sf-amount"
            required
            inputMode="decimal"
            placeholder="0.00"
            value={form.amount}
            onChange={(e) => set("amount", e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Currency</Label>
          <Select
            value={form.currency}
            onValueChange={(v) => set("currency", v)}
          >
            <SelectTrigger aria-label="Currency">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(currencies.data ?? [form.currency]).map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="sf-from">From account</Label>
          <Input
            id="sf-from"
            required
            list="accounts"
            placeholder="Assets:Bank"
            value={form.from_account}
            onChange={(e) => set("from_account", e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sf-to">To account</Label>
          <Input
            id="sf-to"
            required
            list="accounts"
            placeholder="Expenses:Subscriptions"
            value={form.to_account}
            onChange={(e) => set("to_account", e.target.value)}
          />
        </div>
      </div>
      <datalist id="accounts">
        {(accounts.data ?? []).map((a) => (
          <option key={a} value={a} />
        ))}
      </datalist>

      <div className="space-y-1.5">
        <Label htmlFor="sf-narration">Narration</Label>
        <Input
          id="sf-narration"
          placeholder="Optional memo"
          value={form.narration}
          onChange={(e) => set("narration", e.target.value)}
        />
      </div>

      <div>
        <Label>Repeats every</Label>
        <div className="mt-1.5 grid grid-cols-2 gap-3">
          <Input
            aria-label="Repeat count"
            type="number"
            min={1}
            value={form.interval_count}
            onChange={(e) => set("interval_count", Number(e.target.value))}
          />
          <Select
            value={form.interval_unit}
            onValueChange={(v) => set("interval_unit", v as IntervalUnit)}
          >
            <SelectTrigger aria-label="Repeat interval">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {UNITS.map((u) => (
                <SelectItem key={u} value={u} className="capitalize">
                  {u}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sf-anchor">Starting from</Label>
        <Input
          id="sf-anchor"
          type="date"
          required
          value={form.anchor_date}
          onChange={(e) => set("anchor_date", e.target.value)}
        />
      </div>

      <Button type="submit" disabled={create.isPending} className="w-full">
        {create.isPending ? "Saving…" : "Create schedule"}
      </Button>
      {create.isError && (
        <p className="text-sm text-destructive">{String(create.error)}</p>
      )}
    </form>
  );
}
