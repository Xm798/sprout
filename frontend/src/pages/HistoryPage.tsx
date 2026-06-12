import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileWarning, Pencil, RotateCcw, Undo2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
  qk,
  useConfig,
  useHistory,
  useHistoryCheck,
  useReadd,
  useSchedules,
  useUnconfirm,
  useUnskip,
  useWritten,
} from "@/api/hooks";
import { analyzeFlow } from "@/api/postings";
import type { Occurrence, Schedule } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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

/** Destructive confirmation for unconfirm: shows the exact block that will be
 * deleted from the ledger before the occurrence returns to the inbox. */
function EditInInboxDialog({
  occurrence,
  name,
  ledgerRoot,
  open,
  onOpenChange,
}: {
  occurrence: Occurrence;
  name: string;
  ledgerRoot?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const written = useWritten(occurrence.id, open);
  const unconfirm = useUnconfirm();
  const qc = useQueryClient();
  const navigate = useNavigate();

  // A 409 means the confirmed-and-present state changed under the dialog
  // (deleted or duplicated meanwhile): close and re-run the reconcile check.
  const conflict =
    written.error instanceof ApiError && written.error.status === 409;
  useEffect(() => {
    if (open && conflict) {
      onOpenChange(false);
      qc.invalidateQueries({ queryKey: qk.historyCheck });
    }
  }, [open, conflict, onOpenChange, qc]);

  function onConfirm() {
    unconfirm.mutate(occurrence.id, {
      onSuccess: () => {
        onOpenChange(false);
        toast.success(`${name} moved back to the inbox`, {
          action: { label: "Go to inbox", onClick: () => navigate("/") },
        });
      },
      onError: (e) =>
        toast.error(`Couldn't move ${name} back to the inbox`, {
          description: errorMessage(e),
        }),
    });
  }

  const file = writtenFile(written.data?.path, ledgerRoot);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit in inbox</DialogTitle>
          <DialogDescription>
            This deletes the transaction below
            {file ? (
              <>
                {" "}
                from <span className="font-mono">{file}</span>
              </>
            ) : null}{" "}
            and returns the occurrence to the inbox.
          </DialogDescription>
        </DialogHeader>
        <pre className="max-h-56 overflow-auto rounded-lg border border-border/60 bg-background/80 p-3 font-mono text-xs leading-relaxed text-foreground/90">
          {written.isLoading
            ? "Loading transaction…"
            : written.isError
              ? `Failed to load the transaction: ${errorMessage(written.error)}`
              : (written.data?.text ?? "")}
        </pre>
        <p className="text-sm text-warning">
          Any manual edits in this text are deleted with it. The inbox rebuilds
          the transaction from Sprout's stored schedule and overrides, which
          may differ from what is shown here.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={!written.isSuccess || unconfirm.isPending}
          >
            Delete &amp; move to inbox
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
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
  const unconfirm = useUnconfirm();
  const unskip = useUnskip();
  const [editOpen, setEditOpen] = useState(false);
  const name = schedule?.name ?? `Schedule ${occurrence.schedule_id}`;
  const flow = analyzeFlow(schedule?.postings, occurrence.override_amounts);
  const amount = flow.amount ?? schedule?.headline_amount ?? "";
  const currency = flow.currency ?? schedule?.headline_currency ?? undefined;
  const effectiveDate = occurrence.override_date ?? occurrence.due_date;
  const file = writtenFile(occurrence.written_path, ledgerRoot);
  const confirmed = occurrence.status === "confirmed";
  const skipped = occurrence.status === "skipped";

  function onReadd() {
    readd.mutate(occurrence.id, {
      onSuccess: () => toast.success(`Re-added ${name} to the ledger`),
      onError: (e) =>
        toast.error(`Couldn't re-add ${name}`, {
          description: errorMessage(e),
        }),
    });
  }

  // The missing variant of unconfirm: nothing is deleted, so no dialog.
  function onMoveBack() {
    unconfirm.mutate(occurrence.id, {
      onSuccess: () => toast.success(`${name} moved back to the inbox`),
      onError: (e) =>
        toast.error(`Couldn't move ${name} back to the inbox`, {
          description: errorMessage(e),
        }),
    });
  }

  function onUnskip() {
    unskip.mutate(occurrence.id, {
      onSuccess: () => toast.success(`${name} is back in the inbox`),
      onError: (e) =>
        toast.error(`Couldn't unskip ${name}`, {
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

        <div className="flex flex-wrap items-center gap-3">
          <div className="text-right font-mono text-lg font-semibold tabular-nums">
            {formatAmount(amount, currency)}
          </div>
          {confirmed && !missing && (
            <Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="h-4 w-4" />
              Edit in inbox
            </Button>
          )}
          {confirmed && missing && (
            <>
              <Button size="sm" onClick={onReadd} disabled={readd.isPending}>
                <RotateCcw className="h-4 w-4" />
                Re-add
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={onMoveBack}
                disabled={unconfirm.isPending}
              >
                <Undo2 className="h-4 w-4" />
                Move back to inbox
              </Button>
            </>
          )}
          {skipped && (
            <Button
              size="sm"
              variant="outline"
              onClick={onUnskip}
              disabled={unskip.isPending}
            >
              <Undo2 className="h-4 w-4" />
              Unskip
            </Button>
          )}
        </div>
      </div>
      {confirmed && !missing && (
        <EditInInboxDialog
          occurrence={occurrence}
          name={name}
          ledgerRoot={ledgerRoot}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      )}
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
