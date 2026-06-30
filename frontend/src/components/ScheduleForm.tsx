import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import {
  useAccounts,
  useBeanFiles,
  useConfig,
  useCreateSchedule,
  useCurrencies,
  useParseTransaction,
  useUpdateSchedule,
} from "@/api/hooks";
import type {
  Cost,
  IntervalUnit,
  ParsedTransaction,
  Posting,
  Price,
  Schedule,
  ScheduleCreate,
} from "@/api/types";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { DatePicker } from "@/components/ui/date-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { errorMessage } from "@/lib/utils";

// Editing shape: amounts/currencies stay plain strings while typing; an empty
// amount marks an auto-balance leg and is serialized to null on submit.
// cost/price have no form UI but must round-trip untouched when editing a
// schedule that carries them (e.g. created via the API).
interface DraftPosting {
  id: string;
  account: string;
  amount: string;
  currency: string;
  cost?: Cost | null;
  price?: Price | null;
}

type Draft = Omit<ScheduleCreate, "postings" | "target_file"> & {
  postings: DraftPosting[];
  target_file: string;
};

function newLeg(currency = ""): DraftPosting {
  return { id: crypto.randomUUID(), account: "", amount: "", currency };
}

// Stored/parsed Posting -> editable DraftPosting. `freshId` mints a new id for
// parsed legs (a brand-new template); editing preserves the id so the backend
// keeps per-leg overrides on untouched legs.
function postingToDraft(p: Posting, freshId = false): DraftPosting {
  return {
    id: freshId ? crypto.randomUUID() : p.id,
    account: p.account,
    amount: p.amount ?? "",
    currency: p.currency ?? "",
    cost: p.cost,
    price: p.price,
  };
}

// Default: an amount leg + an auto-balance leg — the old "from X to Y" model.
function emptyDraft(currency: string): Draft {
  return {
    name: "",
    payee: "",
    narration: "",
    interval_unit: "month",
    interval_count: 1,
    anchor_date: "",
    end_date: null,
    max_count: null,
    tags: "sprout",
    status: "active",
    target_file: "",
    postings: [newLeg(currency), newLeg("")],
  };
}

// Map a stored schedule back into the editable draft shape. Posting ids are
// preserved so the backend can keep per-leg overrides on untouched legs.
function scheduleToDraft(s: Schedule): Draft {
  return {
    name: s.name,
    payee: s.payee,
    narration: s.narration,
    interval_unit: s.interval_unit,
    interval_count: s.interval_count,
    anchor_date: s.anchor_date,
    end_date: s.end_date,
    max_count: s.max_count,
    tags: s.tags,
    status: s.status,
    target_file: s.target_file ?? "",
    postings: s.postings.map((p) => postingToDraft(p)),
  };
}

// An untouched price row (revealed but left entirely blank) is dropped on
// submit. Anything partially or invalidly filled is caught earlier by
// priceErrorKey, so by the time this runs a non-empty price is valid.
function cleanPrice(price?: Price | null): Price | null {
  if (!price) return null;
  const amount = price.amount.trim();
  const currency = price.currency.trim().toUpperCase();
  if (amount === "" && currency === "") return null;
  return { amount, currency, total: price.total };
}

// Validate a revealed price row. Both-blank is fine (it will be dropped); a row
// with only one of amount/currency, or a non-numeric amount, is a mistake the
// user must fix or clear rather than have silently dropped or 422'd by save.
function priceErrorKey(
  price?: Price | null
): "errorIncomplete" | "errorNotNumber" | null {
  if (!price) return null;
  const amount = price.amount.trim();
  const currency = price.currency.trim();
  if (amount === "" && currency === "") return null;
  if (amount === "" || currency === "") return "errorIncomplete";
  if (!/^-?\d*\.?\d+$/.test(amount)) return "errorNotNumber";
  return null;
}

function toPayload(draft: Draft): ScheduleCreate {
  const postings: Posting[] = draft.postings.map((p) => {
    const amount = p.amount.trim();
    const account = p.account.trim();
    // Blanking the amount turns the leg into an auto-balance leg, which
    // cannot carry cost/price; otherwise annotations pass through untouched.
    return amount === ""
      ? { id: p.id, account, amount: null, currency: null }
      : {
          id: p.id,
          account,
          amount,
          currency: p.currency,
          cost: p.cost ?? null,
          price: cleanPrice(p.price),
        };
  });
  return { ...draft, target_file: draft.target_file.trim() || null, postings };
}

const UNITS: IntervalUnit[] = ["day", "week", "month", "quarter", "year"];

export function ScheduleForm({
  schedule,
  onSaved,
}: {
  schedule?: Schedule; // present = edit mode
  onSaved?: () => void;
}) {
  const { t } = useTranslation();
  const config = useConfig();
  const defaultCurrency = config.data?.default_currency || "USD";
  const [draft, setDraft] = useState<Draft>(() =>
    schedule ? scheduleToDraft(schedule) : emptyDraft(defaultCurrency)
  );
  // The config arrives async; refresh the default currency on a form the user
  // hasn't touched yet, without clobbering in-progress input or a prefilled edit.
  const touched = useRef(false);
  // `schedule` is fixed for a mount (edit dialogs remount per open), so the
  // only live dependency is the currency.
  useEffect(() => {
    if (!schedule && !touched.current) setDraft(emptyDraft(defaultCurrency));
  }, [defaultCurrency]);
  const accounts = useAccounts();
  const currencies = useCurrencies();
  const beanFiles = useBeanFiles();
  const create = useCreateSchedule();
  const update = useUpdateSchedule();
  const parse = useParseTransaction();
  const saving = create.isPending || update.isPending;

  // Paste-and-parse: a create-only shortcut that fills the transaction fields
  // from an existing bean transaction, leaving recurrence fields to the user.
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [importWarnings, setImportWarnings] = useState<string[]>([]);
  // Per-leg price row: which legs the user has revealed, which is mid-fetch,
  // and the provider/date of the last fetched rate (keyed by posting id).
  const [priceOpen, setPriceOpen] = useState<Record<string, boolean>>({});
  const [fetchingId, setFetchingId] = useState<string | null>(null);
  const [rateMeta, setRateMeta] = useState<
    Record<string, { source: string; asOf: string }>
  >({});
  const [priceError, setPriceError] = useState<string | null>(null);

  // Known backend sentinels get a localized message; anything else (raw
  // beancount syntax error) is wrapped so the CN UI never shows a bare blob.
  function importErrorText(detail: string): string {
    if (detail === "no transaction found") return t("scheduleForm.import.noTransaction");
    if (detail === "paste exactly one transaction")
      return t("scheduleForm.import.multipleTransactions");
    return t("scheduleForm.import.parseFailed", { detail });
  }

  function applyParsed(p: ParsedTransaction) {
    touched.current = true;
    setDraft((d) => ({
      ...d,
      // name is the schedule's own label, kept as the user entered it — not imported.
      payee: p.payee,
      narration: p.narration,
      tags: p.tags,
      anchor_date: p.anchor_date,
      postings: p.postings.map((pg) => postingToDraft(pg, true)),
    }));
  }

  function runParse() {
    setImportError(null);
    parse.mutate(
      { text: importText },
      {
        onSuccess: (p) => {
          // Guard against clobbering in-progress input; a pristine form applies
          // freely (that is the whole point), a dirty one asks first.
          if (touched.current && !window.confirm(t("scheduleForm.import.overwriteConfirm")))
            return;
          applyParsed(p);
          setImportWarnings(p.warnings);
        },
        onError: (err) => {
          setImportWarnings([]);
          setImportError(importErrorText(errorMessage(err)));
        },
      }
    );
  }

  const accountOptions = accounts.data ?? [];
  const currencyOptions = currencies.data ?? [];
  const beanFileOptions = beanFiles.data ?? [];
  const targetFileValue = draft.target_file.trim();
  const isNewFile =
    beanFiles.isSuccess &&
    targetFileValue !== "" &&
    !beanFileOptions.includes(targetFileValue);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    touched.current = true;
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function setLeg(id: string, patch: Partial<DraftPosting>) {
    touched.current = true;
    setDraft((d) => ({
      ...d,
      postings: d.postings.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }));
  }

  // Functional update keyed by id: read the *current* price so an in-flight
  // fetch resolving after the user edits the same leg can't clobber it via a
  // stale captured value.
  function setPriceField(legId: string, patch: Partial<Price>) {
    touched.current = true;
    setDraft((d) => ({
      ...d,
      postings: d.postings.map((p) =>
        p.id === legId
          ? {
              ...p,
              price: {
                ...(p.price ?? { amount: "", currency: "", total: false }),
                ...patch,
              },
            }
          : p
      ),
    }));
  }

  function clearPrice(leg: DraftPosting) {
    setLeg(leg.id, { price: null });
    setPriceOpen((o) => ({ ...o, [leg.id]: false }));
    setRateMeta((m) => {
      const { [leg.id]: _drop, ...rest } = m;
      return rest;
    });
  }

  // base = the leg's own commodity, quote = the price currency: `amount X @ rate Y`
  // means rate is Y per X. Fiat pairs route to ECB, crypto pairs to CoinGecko.
  async function fetchRate(leg: DraftPosting) {
    const base = leg.currency.trim().toUpperCase();
    const quote = (leg.price?.currency ?? "").trim().toUpperCase();
    if (!base || !quote) return;
    setFetchingId(leg.id);
    try {
      const q = await api.getExchangeRate(base, quote);
      setPriceField(leg.id, { amount: q.rate, currency: quote });
      setRateMeta((m) => ({ ...m, [leg.id]: { source: q.source, asOf: q.as_of } }));
    } catch (err) {
      toast.error(t("scheduleForm.price.fetchFailedToast"), {
        description: errorMessage(err),
      });
    } finally {
      setFetchingId(null);
    }
  }

  function addLeg() {
    touched.current = true;
    setDraft((d) => ({ ...d, postings: [...d.postings, newLeg(defaultCurrency)] }));
  }

  function removeLeg(id: string) {
    setDraft((d) =>
      d.postings.length <= 2
        ? d
        : { ...d, postings: d.postings.filter((p) => p.id !== id) }
    );
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const errKey = draft.postings
      .map((p) => priceErrorKey(p.price))
      .find((k): k is "errorIncomplete" | "errorNotNumber" => k !== null);
    if (errKey) {
      setPriceError(t(`scheduleForm.price.${errKey}`));
      return;
    }
    setPriceError(null);
    if (schedule) {
      update.mutate(
        { id: schedule.id, body: toPayload(draft) },
        {
          onSuccess: () => onSaved?.(),
          onError: (err) =>
            toast.error(t("scheduleForm.updateFailedToast"), {
              description: errorMessage(err),
            }),
        }
      );
      return;
    }
    create.mutate(toPayload(draft), {
      onSuccess: () => {
        setDraft(emptyDraft(defaultCurrency));
        touched.current = false;
        onSaved?.();
      },
      onError: (err) =>
        toast.error(t("scheduleForm.createFailedToast"), {
          description: errorMessage(err),
        }),
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {!schedule && (
        <div className="rounded-lg border border-border/60">
          <button
            type="button"
            className="flex w-full items-center gap-1.5 px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground"
            aria-expanded={importOpen}
            onClick={() => setImportOpen((o) => !o)}
          >
            {importOpen ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            {t("scheduleForm.import.title")}
          </button>
          {importOpen && (
            <div className="space-y-2 px-3 pb-3">
              <textarea
                aria-label={t("scheduleForm.import.textareaLabel")}
                className="flex min-h-[7rem] w-full rounded-md border border-input bg-background/60 px-3 py-2 font-mono text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
                placeholder={t("scheduleForm.import.placeholder")}
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
              />
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={parse.isPending || importText.trim() === ""}
                onClick={runParse}
              >
                {t("scheduleForm.import.parseButton")}
              </Button>
              {importError && (
                <p role="alert" className="text-sm text-destructive">
                  {importError}
                </p>
              )}
              {importWarnings.length > 0 && (
                <div className="text-sm text-amber-600 dark:text-amber-500">
                  <p className="font-medium">{t("scheduleForm.import.warningsTitle")}</p>
                  <ul className="list-disc pl-5">
                    {importWarnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="sf-name">{t("scheduleForm.name")}</Label>
        <Input
          id="sf-name"
          required
          placeholder={t("scheduleForm.namePlaceholder")}
          value={draft.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>{t("scheduleForm.postings")}</Label>
          <Button type="button" variant="ghost" size="sm" onClick={addLeg}>
            <Plus className="h-4 w-4" />
            {t("scheduleForm.addPosting")}
          </Button>
        </div>

        {draft.postings.map((leg, i) => {
          const blank = leg.amount.trim() === "";
          return (
            <div
              key={leg.id}
              className="space-y-1.5 rounded-lg border border-border/60 p-3"
            >
              <div className="flex items-center justify-between">
                <Label htmlFor={`sf-account-${i}`} className="text-xs">
                  {t("scheduleForm.postingN", { n: i + 1 })}
                  {blank && (
                    <span className="ml-2 font-normal text-muted-foreground">
                      {t("scheduleForm.autoBalanceLeg")}
                    </span>
                  )}
                </Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  aria-label={t("scheduleForm.removePostingN", { n: i + 1 })}
                  disabled={draft.postings.length <= 2}
                  onClick={() => removeLeg(leg.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              <Combobox
                id={`sf-account-${i}`}
                aria-label={t("scheduleForm.accountN", { n: i + 1 })}
                required
                value={leg.account}
                onChange={(v) => setLeg(leg.id, { account: v })}
                suggestions={accountOptions}
                placeholder={t("scheduleForm.accountPlaceholder")}
              />

              <div className="grid grid-cols-3 gap-2">
                <Input
                  className="col-span-2"
                  aria-label={t("scheduleForm.amountN", { n: i + 1 })}
                  inputMode="decimal"
                  placeholder={t("scheduleForm.amountPlaceholder")}
                  value={leg.amount}
                  onChange={(e) => setLeg(leg.id, { amount: e.target.value })}
                />
                <Combobox
                  aria-label={t("scheduleForm.currencyN", { n: i + 1 })}
                  value={blank ? "" : leg.currency}
                  onChange={(v) => setLeg(leg.id, { currency: v })}
                  suggestions={currencyOptions}
                  transform={(v) => v.toUpperCase()}
                  placeholder={defaultCurrency}
                />
              </div>

              {!blank &&
                (leg.price || priceOpen[leg.id] ? (
                  <div className="space-y-1.5 rounded-md bg-muted/40 p-2">
                    <div className="grid grid-cols-[auto_1fr_1fr] items-center gap-2">
                      <span className="font-mono text-sm text-muted-foreground">@</span>
                      <Input
                        aria-label={t("scheduleForm.priceN", { n: i + 1 })}
                        inputMode="decimal"
                        placeholder={t("scheduleForm.price.amountPlaceholder")}
                        value={leg.price?.amount ?? ""}
                        onChange={(e) => setPriceField(leg.id, { amount: e.target.value })}
                      />
                      <Combobox
                        aria-label={t("scheduleForm.priceCurrencyN", { n: i + 1 })}
                        value={leg.price?.currency ?? ""}
                        onChange={(v) => setPriceField(leg.id, { currency: v })}
                        suggestions={currencyOptions}
                        transform={(v) => v.toUpperCase()}
                        placeholder={t("scheduleForm.price.currencyPlaceholder")}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={
                          fetchingId === leg.id ||
                          !leg.currency.trim() ||
                          !(leg.price?.currency ?? "").trim()
                        }
                        onClick={() => fetchRate(leg)}
                      >
                        {fetchingId === leg.id
                          ? t("scheduleForm.price.fetching")
                          : t("scheduleForm.price.fetch")}
                      </Button>
                      {rateMeta[leg.id] && (
                        <span className="text-xs text-muted-foreground">
                          {rateMeta[leg.id].source} · {rateMeta[leg.id].asOf}
                        </span>
                      )}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="ml-auto text-muted-foreground"
                        onClick={() => clearPrice(leg)}
                      >
                        {t("scheduleForm.price.remove")}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hover:text-foreground"
                    onClick={() =>
                      setPriceOpen((o) => ({ ...o, [leg.id]: true }))
                    }
                  >
                    + {t("scheduleForm.price.add")}
                  </button>
                ))}
            </div>
          );
        })}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sf-payee">{t("scheduleForm.payee")}</Label>
        <Input
          id="sf-payee"
          placeholder={t("scheduleForm.payeePlaceholder")}
          value={draft.payee}
          onChange={(e) => set("payee", e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sf-narration">{t("scheduleForm.narration")}</Label>
        <Input
          id="sf-narration"
          placeholder={t("scheduleForm.narrationPlaceholder")}
          value={draft.narration}
          onChange={(e) => set("narration", e.target.value)}
        />
      </div>

      <div>
        <Label>{t("scheduleForm.repeatsEvery")}</Label>
        <div className="mt-1.5 grid grid-cols-2 gap-3">
          <Input
            aria-label={t("scheduleForm.repeatCount")}
            type="number"
            min={1}
            value={draft.interval_count}
            onChange={(e) => set("interval_count", Number(e.target.value))}
          />
          <Select
            value={draft.interval_unit}
            onValueChange={(v) => set("interval_unit", v as IntervalUnit)}
          >
            <SelectTrigger aria-label={t("scheduleForm.repeatInterval")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {UNITS.map((u) => (
                <SelectItem key={u} value={u}>
                  {t(`scheduleForm.unit.${u}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sf-anchor">{t("scheduleForm.startingFrom")}</Label>
        <DatePicker
          id="sf-anchor"
          aria-label={t("scheduleForm.startingFrom")}
          value={draft.anchor_date}
          onChange={(v) => set("anchor_date", v)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sf-target-file">{t("scheduleForm.targetFile")}</Label>
        <Combobox
          id="sf-target-file"
          aria-label={t("scheduleForm.targetFile")}
          value={draft.target_file}
          onChange={(v) => set("target_file", v)}
          suggestions={beanFileOptions}
          placeholder={t("scheduleForm.targetFilePlaceholder")}
        />
        {isNewFile && (
          <p className="text-xs text-muted-foreground">
            {t("scheduleForm.newFileHint")}
          </p>
        )}
      </div>

      {priceError && (
        <p role="alert" className="text-sm text-destructive">
          {priceError}
        </p>
      )}

      <Button type="submit" disabled={saving} className="w-full">
        {saving ? t("common.saving") : schedule ? t("scheduleForm.saveChanges") : t("scheduleForm.create")}
      </Button>
    </form>
  );
}
