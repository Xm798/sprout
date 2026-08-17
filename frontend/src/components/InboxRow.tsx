import { useState } from "react";
import { Check, ChevronDown, SkipForward, Wallet } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

import { useConfirm, useMarkPaidOutside, usePreview, useSkip } from "@/api/hooks";
import { analyzeFlow, headlineDisplay } from "@/api/postings";
import type { ConfirmBody, Occurrence, Schedule } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DatePicker } from "@/components/ui/date-picker";
import { FlowAccounts } from "@/components/FlowAccounts";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { cn, errorMessage, formatAmount, formatDate, leafAccount } from "@/lib/utils";

export function InboxRow({
  occurrence,
  schedule,
}: {
  occurrence: Occurrence;
  schedule?: Schedule;
}) {
  const { t } = useTranslation();
  const isLoan = schedule?.kind === "loan";
  const [expanded, setExpanded] = useState(() => isLoan);
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [date, setDate] = useState("");
  const [narration, setNarration] = useState("");

  const confirm = useConfirm();
  const skip = useSkip();
  const markPaidOutside = useMarkPaidOutside();

  // Overdue: loan occurrence pending past its due date — visual flag only.
  const today = new Date().toISOString().slice(0, 10);
  const isOverdue = isLoan && occurrence.status === "pending" && occurrence.due_date < today;

  const name = schedule?.name ?? t("common.scheduleFallback", { id: occurrence.schedule_id });
  // Headline = net flow of the auto-balance leg.
  const flow = analyzeFlow(schedule?.postings, occurrence.override_amounts);
  const { amount: baseAmount = "", currency: baseCurrency } = headlineDisplay(
    flow,
    schedule
  );
  // Every posting gets its own input, in schedule posting order — analyzeFlow
  // groups/omits legs (e.g. its fallback mode only surfaces 1-2), so it isn't
  // a complete leg list. Flow legs are only consulted for a derived amount to
  // show on blank (posting.amount == null) legs.
  const postings = schedule?.postings ?? [];
  const flowLegById = new Map(
    [...flow.sources, ...flow.destinations].map((l) => [l.posting.id, l])
  );
  const effectiveDate = occurrence.override_date ?? occurrence.due_date;
  const fieldId = `occ-${occurrence.id}`;

  // Collect the row's edits into a request body; omit untouched fields so the
  // backend keeps any persisted overrides.
  function buildBody(): ConfirmBody {
    const body: ConfirmBody = {};
    const typed = Object.entries(amounts).filter(([, v]) => v);
    if (typed.length > 0) {
      body.override_amounts = Object.fromEntries(typed);
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
        onSuccess: () => toast.success(t("inboxRow.confirmedToast", { name })),
        onError: (e) =>
          toast.error(t("inboxRow.confirmFailedToast", { name }), {
            description: errorMessage(e),
          }),
      }
    );
  }

  function onSkip() {
    skip.mutate(occurrence.id, {
      onSuccess: () => toast.success(t("inboxRow.skippedToast", { name })),
    });
  }

  function onPaidOutside() {
    markPaidOutside.mutate(occurrence.id, {
      onSuccess: () => toast.success(t("inboxRow.paidOutsideToast", { name })),
      onError: (e) =>
        toast.error(t("inboxRow.paidOutsideFailedToast", { name }), {
          description: errorMessage(e),
        }),
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
            <Badge variant="warning">{t(`common.status.${occurrence.status}`)}</Badge>
            {isOverdue && (
              <Badge variant="destructive">{t("inboxRow.needsAttention")}</Badge>
            )}
          </div>
          <div className="flex min-w-0 items-center gap-1.5 text-sm text-muted-foreground">
            <FlowAccounts flow={flow} />
          </div>
          <p className="text-xs text-muted-foreground">
            {t("inboxRow.due", { date: formatDate(effectiveDate) })}
          </p>
        </div>

        <div className="text-right">
          <div className="font-mono text-lg font-semibold tabular-nums">
            {formatAmount(baseAmount, baseCurrency)}
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
          {t("inboxRow.confirm")}
        </Button>
        {isLoan ? (
          <Button
            size="sm"
            variant="outline"
            onClick={onPaidOutside}
            disabled={markPaidOutside.isPending}
            className="flex-1 sm:flex-none"
          >
            <Wallet className="h-4 w-4" />
            {t("inboxRow.paidOutside")}
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={onSkip}
            disabled={skip.isPending}
            className="flex-1 sm:flex-none"
          >
            <SkipForward className="h-4 w-4" />
            {t("inboxRow.skip")}
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto text-muted-foreground"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? t("inboxRow.hide") : t("inboxRow.preview")}
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
              <Label>{t("inboxRow.amount")}</Label>
              <div className="space-y-2">
                {postings.map((posting) => {
                  const disabled = posting.amount == null;
                  const legId = `${fieldId}-amount-${posting.id}`;
                  const derivedAmount = flowLegById.get(posting.id)?.amount;
                  const placeholder = disabled
                    ? derivedAmount != null
                      ? String(derivedAmount)
                      : "—"
                    : occurrence.override_amounts[posting.id] ?? posting.amount ?? "";
                  return (
                    <div key={posting.id} className="space-y-1">
                      <Label
                        htmlFor={legId}
                        className="text-xs font-normal text-muted-foreground"
                      >
                        {leafAccount(posting.account)}
                      </Label>
                      <Input
                        id={legId}
                        inputMode="decimal"
                        disabled={disabled}
                        placeholder={placeholder}
                        value={amounts[posting.id] ?? ""}
                        onChange={(e) =>
                          setAmounts((prev) => ({ ...prev, [posting.id]: e.target.value }))
                        }
                      />
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${fieldId}-date`}>{t("inboxRow.date")}</Label>
              <DatePicker
                id={`${fieldId}-date`}
                aria-label={t("inboxRow.overrideDate")}
                value={date}
                onChange={setDate}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${fieldId}-narration`}>{t("inboxRow.narration")}</Label>
              <Input
                id={`${fieldId}-narration`}
                placeholder={t("inboxRow.overrideNarration")}
                value={narration}
                onChange={(e) => setNarration(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>{t("inboxRow.beancountPreview")}</Label>
            <pre className="max-h-56 overflow-auto rounded-lg border border-border/60 bg-background/80 p-3 font-mono text-xs leading-relaxed text-foreground/90">
              {preview.isLoading
                ? t("common.loading")
                : preview.isError
                  ? t("inboxRow.previewFailed")
                  : preview.data?.text ?? ""}
            </pre>
          </div>

          {confirm.isError && (
            <p className="text-sm text-destructive">
              {errorMessage(confirm.error)}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
