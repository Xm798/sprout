import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import {
  useAddScheduleEvent,
  useDeleteScheduleEvent,
  usePreviewAmortization,
} from "@/api/hooks";
import type {
  AmortizationEvent,
  AmortizationResult,
  LoanData,
  PrepaymentMode,
  ScheduleEventBody,
} from "@/api/types";
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
import { cn, errorMessage, formatAmount, formatDate, percentToDecimal } from "@/lib/utils";

const PREPAY_MODES: PrepaymentMode[] = ["shorten_term", "reduce_payment"];

interface AmortizationTableProps {
  loan: LoanData; // annual_rate is already a decimal string
  anchorDate: string;
  intervalCount: number;
  currency?: string;
  // When present, the table drives a saved schedule and shows event actions.
  scheduleId?: number;
  events?: AmortizationEvent[];
}

// The draft loan is complete enough to render a preview.
function loanReady(loan: LoanData, anchorDate: string): boolean {
  return (
    anchorDate.trim() !== "" &&
    Number(loan.principal) > 0 &&
    Number.isFinite(loan.term_count) &&
    loan.term_count > 0
  );
}

export function AmortizationTable({
  loan,
  anchorDate,
  intervalCount,
  currency,
  scheduleId,
  events: initialEvents = [],
}: AmortizationTableProps) {
  const { t } = useTranslation();
  // The events list is local so adding/removing one on a saved schedule
  // re-runs the preview immediately.
  const [events, setEvents] = useState<AmortizationEvent[]>(initialEvents);

  const enabled = loanReady(loan, anchorDate);
  const body = { loan, anchor_date: anchorDate, interval_count: intervalCount, events };
  const preview = usePreviewAmortization(body, enabled);

  if (!enabled) {
    return (
      <p className="text-sm text-muted-foreground">
        {t("amortization.fillToPreview")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label className="text-sm">{t("amortization.title")}</Label>
        {preview.isFetching && (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        )}
      </div>

      {preview.isError ? (
        <p role="alert" className="text-sm text-destructive">
          {t("amortization.previewFailed", { error: errorMessage(preview.error) })}
        </p>
      ) : preview.data ? (
        <PreviewBody data={preview.data} currency={currency} />
      ) : (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      )}

      {scheduleId != null && preview.data && (
        <EventActions
          scheduleId={scheduleId}
          dueDates={preview.data.rows.map((r) => r.due_date)}
          events={events}
          onChange={setEvents}
        />
      )}
    </div>
  );
}

function PreviewBody({
  data,
  currency,
}: {
  data: AmortizationResult;
  currency?: string;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span>
          <span className="text-muted-foreground">{t("amortization.totalInterest")}: </span>
          <span className="font-mono font-semibold tabular-nums">
            {formatAmount(data.total_interest, currency)}
          </span>
        </span>
        <span>
          <span className="text-muted-foreground">{t("amortization.payoffDate")}: </span>
          <span className="font-medium">{formatDate(data.payoff_date)}</span>
        </span>
      </div>

      <div className="max-h-72 overflow-auto rounded-lg border border-border/60">
        <table className="w-full text-right text-sm tabular-nums">
          <thead className="sticky top-0 bg-muted/80 text-xs text-muted-foreground backdrop-blur">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium">{t("amortization.seq")}</th>
              <th className="px-2 py-1.5 text-left font-medium">{t("amortization.dueDate")}</th>
              <th className="px-2 py-1.5 font-medium">{t("amortization.principal")}</th>
              <th className="px-2 py-1.5 font-medium">{t("amortization.interest")}</th>
              <th className="px-2 py-1.5 font-medium">{t("amortization.payment")}</th>
              <th className="px-2 py-1.5 font-medium">{t("amortization.balance")}</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr
                key={`${row.seq}-${row.due_date}-${row.event_id ?? ""}`}
                className={cn(
                  "border-t border-border/40",
                  row.is_prepayment && "bg-primary/10 font-medium text-primary"
                )}
              >
                <td className="px-2 py-1 text-left">
                  {row.seq}
                  {row.is_prepayment && (
                    <span className="ml-1 text-xs">{t("amortization.prepaymentTag")}</span>
                  )}
                </td>
                <td className="px-2 py-1 text-left font-mono">{row.due_date}</td>
                <td className="px-2 py-1 font-mono">{formatAmount(row.principal)}</td>
                <td className="px-2 py-1 font-mono">{formatAmount(row.interest)}</td>
                <td className="px-2 py-1 font-mono">{formatAmount(row.payment)}</td>
                <td className="px-2 py-1 font-mono">{formatAmount(row.balance_after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// Prepayment + rate-change forms for a saved schedule. Dates are constrained to
// the previewed payment dates; the backend still 422s anything on or before the
// last confirmed installment, which we surface as a toast.
function EventActions({
  scheduleId,
  dueDates,
  events,
  onChange,
}: {
  scheduleId: number;
  dueDates: string[];
  events: AmortizationEvent[];
  onChange: (events: AmortizationEvent[]) => void;
}) {
  const { t } = useTranslation();
  const add = useAddScheduleEvent();
  const del = useDeleteScheduleEvent();

  const [kind, setKind] = useState<"prepayment" | "rate_change">("prepayment");
  const [date, setDate] = useState("");
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<PrepaymentMode>("shorten_term");
  const [ratePct, setRatePct] = useState("");

  function submit() {
    const chosen = date || dueDates[0];
    if (!chosen) return;
    const payload: ScheduleEventBody =
      kind === "prepayment"
        ? { kind: "prepayment", date: chosen, amount, mode }
        : { kind: "rate_change", date: chosen, annual_rate: percentToDecimal(ratePct) };
    add.mutate(
      { id: scheduleId, body: payload },
      {
        onSuccess: (schedule) => {
          onChange(schedule.events ?? [...events, payload as AmortizationEvent]);
          setDate("");
          setAmount("");
          setRatePct("");
          toast.success(t("amortization.eventAddedToast"));
        },
        onError: (err) =>
          toast.error(t("amortization.eventFailedToast"), {
            description: errorMessage(err),
          }),
      }
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-border/60 p-3">
      <div className="space-y-1.5">
        <Label className="text-xs">{t("amortization.eventKind")}</Label>
        <Select value={kind} onValueChange={(v) => setKind(v as typeof kind)}>
          <SelectTrigger aria-label={t("amortization.eventKind")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="prepayment">{t("amortization.prepayment")}</SelectItem>
            <SelectItem value="rate_change">{t("amortization.rateChange")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">{t("amortization.eventDate")}</Label>
        <Select value={date || dueDates[0]} onValueChange={setDate}>
          <SelectTrigger aria-label={t("amortization.eventDate")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {dueDates.map((d) => (
              <SelectItem key={d} value={d}>
                {formatDate(d)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {kind === "prepayment" ? (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="amort-prepay-amount" className="text-xs">
              {t("amortization.prepaymentAmount")}
            </Label>
            <Input
              id="amort-prepay-amount"
              aria-label={t("amortization.prepaymentAmount")}
              inputMode="decimal"
              placeholder={t("amortization.prepaymentAmountPlaceholder")}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("amortization.prepaymentMode")}</Label>
            <Select value={mode} onValueChange={(v) => setMode(v as PrepaymentMode)}>
              <SelectTrigger aria-label={t("amortization.prepaymentMode")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PREPAY_MODES.map((m) => (
                  <SelectItem key={m} value={m}>
                    {t(`amortization.mode.${m}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="amort-rate" className="text-xs">
            {t("amortization.newRate")}
          </Label>
          <Input
            id="amort-rate"
            aria-label={t("amortization.newRate")}
            inputMode="decimal"
            placeholder={t("amortization.newRatePlaceholder")}
            value={ratePct}
            onChange={(e) => setRatePct(e.target.value)}
          />
        </div>
      )}

      <Button type="button" size="sm" disabled={add.isPending} onClick={submit}>
        {add.isPending ? t("common.saving") : t("amortization.addEvent")}
      </Button>

      {events.length > 0 && (
        <ul className="space-y-1 pt-1">
          {events.map((ev) => (
            <li
              key={ev.id ?? `${ev.kind}-${ev.date}`}
              className="flex items-center justify-between gap-2 text-xs text-muted-foreground"
            >
              <span>
                {ev.kind === "prepayment"
                  ? t("amortization.prepayment")
                  : t("amortization.rateChange")}{" "}
                · {formatDate(ev.date)}
                {ev.kind === "prepayment" && ev.amount ? ` · ${formatAmount(ev.amount)}` : ""}
              </span>
              {ev.id != null && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 hover:text-destructive"
                  aria-label={t("amortization.removeEvent")}
                  disabled={del.isPending}
                  onClick={() =>
                    del.mutate(
                      { id: scheduleId, eventId: ev.id! },
                      {
                        onSuccess: (schedule) =>
                          onChange(
                            schedule.events ?? events.filter((e) => e.id !== ev.id)
                          ),
                        onError: (err) =>
                          toast.error(t("amortization.eventFailedToast"), {
                            description: errorMessage(err),
                          }),
                      }
                    )
                  }
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
