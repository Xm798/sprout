import { CheckCheck } from "lucide-react";
import { toast } from "sonner";

import { useConfirm, useInbox, useSchedules } from "@/api/hooks";
import { InboxRow } from "@/components/InboxRow";
import { SproutMark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAmount } from "@/lib/utils";

export function InboxPage() {
  const inbox = useInbox();
  const schedules = useSchedules();
  const confirm = useConfirm();

  const byId = new Map((schedules.data ?? []).map((s) => [s.id, s]));
  const items = inbox.data ?? [];

  // Sum the amount due per currency, using overrides where present.
  const totals = new Map<string, number>();
  for (const occ of items) {
    const sch = byId.get(occ.schedule_id);
    const raw = occ.override_amount ?? sch?.amount;
    const currency = sch?.currency ?? "";
    const n = Number(raw);
    if (!Number.isNaN(n)) totals.set(currency, (totals.get(currency) ?? 0) + n);
  }
  const totalLabel = Array.from(totals.entries())
    .map(([currency, sum]) => formatAmount(sum, currency))
    .join(" · ");

  function confirmAll() {
    items.forEach((o) => confirm.mutate({ id: o.id, body: {} }));
    toast.success(`Confirming ${items.length} occurrence(s)`);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            Inbox
          </h1>
          <p className="text-sm text-muted-foreground">
            {items.length > 0
              ? `${items.length} due${totalLabel ? ` · ${totalLabel}` : ""}`
              : "Review and confirm what's due."}
          </p>
        </div>
        {items.length > 0 && (
          <Button
            variant="outline"
            onClick={confirmAll}
            disabled={confirm.isPending}
          >
            <CheckCheck className="h-4 w-4" />
            Confirm all
          </Button>
        )}
      </header>

      {inbox.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-lg" />
          ))}
        </div>
      ) : inbox.isError ? (
        <Card>
          <CardContent className="p-6 text-center text-sm text-destructive">
            Failed to load inbox. Check that the API is reachable.
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <Card className="border-dashed bg-card/50">
          <CardContent className="flex flex-col items-center gap-3 px-6 py-14 text-center">
            <span className="grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary">
              <SproutMark className="h-8 w-8" />
            </span>
            <div className="space-y-1">
              <p className="font-display text-lg font-semibold">
                You're all caught up
              </p>
              <p className="text-sm text-muted-foreground">
                Nothing is due right now. New occurrences appear here as they
                come around.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((occ, i) => (
            <div
              key={occ.id}
              className="animate-fade-up"
              style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
            >
              <InboxRow occurrence={occ} schedule={byId.get(occ.schedule_id)} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
