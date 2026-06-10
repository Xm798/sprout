import { useState } from "react";
import { ArrowRight, Check, ChevronDown, SkipForward } from "lucide-react";
import { toast } from "sonner";

import { useConfirm, usePreview, useSkip } from "@/api/hooks";
import type { ConfirmBody, Occurrence, Schedule } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DatePicker } from "@/components/ui/date-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { cn, errorMessage, formatAmount } from "@/lib/utils";

function formatDate(value: string) {
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function leaf(account?: string) {
  if (!account) return "—";
  const parts = account.split(":");
  return parts[parts.length - 1] || account;
}

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

  const name = schedule?.name ?? `Schedule ${occurrence.schedule_id}`;
  // Headline = first amount-bearing leg; edits in this row tune that leg.
  const amountLeg = schedule?.postings.find((p) => p.amount != null);
  const blankLeg = schedule?.postings.find((p) => p.amount == null);
  const headlineId = amountLeg?.id;
  const storedOverride =
    headlineId != null ? occurrence.override_amounts[headlineId] : undefined;
  const baseAmount = storedOverride ?? schedule?.headline_amount ?? "";
  const effectiveDate = occurrence.override_date ?? occurrence.due_date;
  const fieldId = `occ-${occurrence.id}`;

  // Collect the row's edits into a request body; omit untouched fields so the
  // backend keeps any persisted overrides.
  function buildBody(): ConfirmBody {
    const body: ConfirmBody = {};
    if (amount && headlineId != null) {
      body.override_amounts = { [headlineId]: amount };
    }
    if (date) body.override_date = date;
    if (narration) body.override_narration = narration;
    return body;
  }

  const preview = usePreview(occurrence.id, buildBody(), expanded);

  function onConfirm() {
    confirm.mutate(
      { id: occurrence.id, body: buildBody() },
      {
        onSuccess: () => toast.success(`Confirmed ${name}`),
        onError: (e) =>
          toast.error(`Couldn't confirm ${name}`, {
            description: errorMessage(e),
          }),
      }
    );
  }

  function onSkip() {
    skip.mutate(occurrence.id, {
      onSuccess: () => toast(`Skipped ${name}`),
    });
  }

  return (
    <Card className="overflow-hidden transition-shadow hover:shadow-lift">
      <div className="flex flex-wrap items-start justify-between gap-4 p-4 sm:p-5">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="truncate font-display text-base font-semibold">
              {name}
            </h3>
            <Badge variant="warning" className="capitalize">
              {occurrence.status}
            </Badge>
          </div>
          <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <span>{leaf(amountLeg?.account)}</span>
            <ArrowRight className="h-3.5 w-3.5 shrink-0 opacity-70" />
            <span>{leaf(blankLeg?.account)}</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Due {formatDate(effectiveDate)}
          </p>
        </div>

        <div className="text-right">
          <div className="font-mono text-lg font-semibold tabular-nums">
            {formatAmount(baseAmount, schedule?.headline_currency ?? undefined)}
          </div>
        </div>
      </div>

      <Separator />

      <div className="flex flex-wrap items-center gap-2 p-3 sm:px-5">
        <Button
          size="sm"
          onClick={onConfirm}
          disabled={confirm.isPending}
          className="flex-1 sm:flex-none"
        >
          <Check className="h-4 w-4" />
          Confirm
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onSkip}
          disabled={skip.isPending}
          className="flex-1 sm:flex-none"
        >
          <SkipForward className="h-4 w-4" />
          Skip
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto text-muted-foreground"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Hide" : "Preview"}
          <ChevronDown
            className={cn(
              "h-4 w-4 transition-transform",
              expanded && "rotate-180"
            )}
          />
        </Button>
      </div>

      {expanded && (
        <div className="space-y-4 border-t border-border/60 bg-muted/30 p-4 sm:p-5">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor={`${fieldId}-amount`}>
                Amount{amountLeg ? ` · ${leaf(amountLeg.account)}` : ""}
              </Label>
              <Input
                id={`${fieldId}-amount`}
                inputMode="decimal"
                disabled={headlineId == null}
                placeholder={String(baseAmount)}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${fieldId}-date`}>Date</Label>
              <DatePicker
                id={`${fieldId}-date`}
                aria-label="Override date"
                value={date}
                onChange={setDate}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${fieldId}-narration`}>Narration</Label>
              <Input
                id={`${fieldId}-narration`}
                placeholder="Override narration"
                value={narration}
                onChange={(e) => setNarration(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Beancount preview</Label>
            <pre className="max-h-56 overflow-auto rounded-lg border border-border/60 bg-background/80 p-3 font-mono text-xs leading-relaxed text-foreground/90">
              {preview.isLoading
                ? "Loading…"
                : preview.isError
                  ? "Failed to render preview."
                  : preview.data?.text ?? ""}
            </pre>
          </div>

          {confirm.isError && (
            <p className="text-sm text-destructive">{String(confirm.error)}</p>
          )}
        </div>
      )}
    </Card>
  );
}
