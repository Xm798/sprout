import { FileWarning, RotateCcw } from "lucide-react";
import { toast } from "sonner";

import {
  useConfig,
  useHistory,
  useHistoryCheck,
  useReadd,
  useSchedules,
} from "@/api/hooks";
import { effectiveHeadlineAmount } from "@/api/postings";
import type { Occurrence, Schedule } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage, formatAmount, formatDate } from "@/lib/utils";

/** Written path relative to the ledger root, for compact display. */
function writtenFile(path?: string | null, root?: string) {
  if (!path) return null;
  if (root) {
    // Path-prefix match, not string-prefix: /fin must not match /finance/x.
    const dir = root.endsWith("/") ? root : `${root}/`;
    if (path.startsWith(dir)) return path.slice(dir.length);
  }
  return path;
}

function HistoryRow({
  occurrence,
  schedule,
  ledgerRoot,
  missing,
}: {
  occurrence: Occurrence;
  schedule?: Schedule;
  ledgerRoot?: string;
  missing: boolean;
}) {
  const readd = useReadd();
  const name = schedule?.name ?? `Schedule ${occurrence.schedule_id}`;
  const amount = effectiveHeadlineAmount(occurrence, schedule) ?? "";
  const effectiveDate = occurrence.override_date ?? occurrence.due_date;
  const file = writtenFile(occurrence.written_path, ledgerRoot);
  const confirmed = occurrence.status === "confirmed";

  function onReadd() {
    readd.mutate(occurrence.id, {
      onSuccess: () => toast.success(`Re-added ${name} to the ledger`),
      onError: (e) =>
        toast.error(`Couldn't re-add ${name}`, {
          description: errorMessage(e),
        }),
    });
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 p-4 sm:p-5">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-display text-base font-semibold">
              {name}
            </h3>
            <Badge
              variant={confirmed ? "success" : "secondary"}
              className="capitalize"
            >
              {occurrence.status}
            </Badge>
            {missing && (
              <Badge variant="destructive">
                <FileWarning className="h-3 w-3" />
                Missing from ledger
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {formatDate(effectiveDate)}
            {confirmed && file ? ` · ${file}` : ""}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right font-mono text-lg font-semibold tabular-nums">
            {formatAmount(amount, schedule?.headline_currency ?? undefined)}
          </div>
          {missing && (
            <Button size="sm" onClick={onReadd} disabled={readd.isPending}>
              <RotateCcw className="h-4 w-4" />
              Re-add
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}

export function HistoryPage() {
  const history = useHistory();
  const schedules = useSchedules();
  const config = useConfig();
  const check = useHistoryCheck();

  const byId = new Map((schedules.data ?? []).map((s) => [s.id, s]));
  const items = history.data ?? [];
  const missing = new Set(check.data?.missing ?? []);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header className="space-y-1">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          History
        </h1>
        <p className="text-sm text-muted-foreground">
          {missing.size > 0
            ? `${missing.size} written transaction(s) missing from the ledger.`
            : "Confirmed and skipped occurrences, checked against your ledger."}
        </p>
        {check.isError && (
          <p className="text-sm text-warning">
            Ledger check failed: {errorMessage(check.error)}
          </p>
        )}
      </header>

      {history.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      ) : history.isError ? (
        <Card>
          <CardContent className="p-6 text-center text-sm text-destructive">
            Failed to load history. Check that the API is reachable.
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <Card className="border-dashed bg-card/50">
          <CardContent className="px-6 py-14 text-center">
            <p className="font-display text-lg font-semibold">No history yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Occurrences you confirm or skip in the inbox will show up here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((occ) => (
            <HistoryRow
              key={occ.id}
              occurrence={occ}
              schedule={byId.get(occ.schedule_id)}
              ledgerRoot={config.data?.ledger_root}
              missing={missing.has(occ.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
