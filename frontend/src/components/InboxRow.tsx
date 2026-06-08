import { useState } from "react";
import { useConfirm, usePreview, useSkip } from "../api/hooks";
import type { Occurrence, Schedule } from "../api/types";

export function InboxRow({
  occurrence,
  schedule,
}: {
  occurrence: Occurrence;
  schedule?: Schedule;
}) {
  const [expanded, setExpanded] = useState(false);
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [narration, setNarration] = useState("");

  const confirm = useConfirm();
  const skip = useSkip();
  const preview = usePreview(occurrence.id, expanded);

  const baseAmount = occurrence.override_amount ?? schedule?.amount ?? "";
  const effectiveDate = occurrence.override_date ?? occurrence.due_date;

  function onConfirm() {
    confirm.mutate({
      id: occurrence.id,
      body: {
        override_amount: amount || null,
        override_date: date || null,
        override_narration: narration || null,
      },
    });
  }

  return (
    <div className="mb-2 rounded border p-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-medium">
            {schedule?.name ?? `Schedule ${occurrence.schedule_id}`}
          </div>
          <div className="text-sm text-gray-600">
            {effectiveDate} · {String(baseAmount)} {schedule?.currency ?? ""}
          </div>
          <div className="text-xs text-gray-500">
            {schedule?.to_account} ← {schedule?.from_account}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            className="text-sm underline"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Hide" : "Preview"}
          </button>
          <button
            className="rounded bg-green-600 px-3 py-1 text-white disabled:opacity-50"
            onClick={onConfirm}
            disabled={confirm.isPending}
          >
            Confirm
          </button>
          <button
            className="rounded border px-3 py-1 disabled:opacity-50"
            onClick={() => skip.mutate(occurrence.id)}
            disabled={skip.isPending}
          >
            Skip
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <label className="text-sm">
              Amount
              <input
                className="w-full rounded border px-2 py-1"
                placeholder={String(baseAmount)}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
            <label className="text-sm">
              Date
              <input
                type="date"
                className="w-full rounded border px-2 py-1"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
            <label className="text-sm">
              Narration
              <input
                className="w-full rounded border px-2 py-1"
                value={narration}
                onChange={(e) => setNarration(e.target.value)}
              />
            </label>
          </div>
          <pre className="overflow-auto rounded border bg-gray-50 p-2 text-xs">
            {preview.isLoading ? "Loading…" : preview.data?.text ?? ""}
          </pre>
          {confirm.isError && (
            <div className="text-sm text-red-600">{String(confirm.error)}</div>
          )}
        </div>
      )}
    </div>
  );
}
