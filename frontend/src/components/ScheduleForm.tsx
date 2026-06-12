import { useState } from "react";
import type { FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { useAccounts, useBeanFiles, useCreateSchedule, useCurrencies } from "@/api/hooks";
import type { IntervalUnit, Posting, ScheduleCreate } from "@/api/types";
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
interface DraftPosting {
  id: string;
  account: string;
  amount: string;
  currency: string;
}

type Draft = Omit<ScheduleCreate, "postings" | "target_file"> & {
  postings: DraftPosting[];
  target_file: string;
};

function newLeg(currency = "USD"): DraftPosting {
  return { id: crypto.randomUUID(), account: "", amount: "", currency };
}

// Default: an amount leg + an auto-balance leg — the old "from X to Y" model.
function emptyDraft(): Draft {
  return {
    name: "",
    narration: "",
    interval_unit: "month",
    interval_count: 1,
    anchor_date: "",
    end_date: null,
    max_count: null,
    tags: "sprout",
    status: "active",
    target_file: "",
    postings: [newLeg("USD"), newLeg("")],
  };
}

function toPayload(draft: Draft): ScheduleCreate {
  const postings: Posting[] = draft.postings.map((p) => {
    const amount = p.amount.trim();
    const account = p.account.trim();
    return amount === ""
      ? { id: p.id, account, amount: null, currency: null }
      : { id: p.id, account, amount, currency: p.currency };
  });
  return { ...draft, target_file: draft.target_file.trim() || null, postings };
}

const UNITS: IntervalUnit[] = ["day", "week", "month", "quarter", "year"];

export function ScheduleForm({ onCreated }: { onCreated?: () => void }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const accounts = useAccounts();
  const currencies = useCurrencies();
  const beanFiles = useBeanFiles();
  const create = useCreateSchedule();

  const accountOptions = accounts.data ?? [];
  const currencyOptions = currencies.data ?? [];
  const beanFileOptions = beanFiles.data ?? [];
  const targetFileValue = draft.target_file.trim();
  const isNewFile =
    beanFiles.isSuccess &&
    targetFileValue !== "" &&
    !beanFileOptions.includes(targetFileValue);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function setLeg(id: string, patch: Partial<DraftPosting>) {
    setDraft((d) => ({
      ...d,
      postings: d.postings.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }));
  }

  function addLeg() {
    setDraft((d) => ({ ...d, postings: [...d.postings, newLeg("USD")] }));
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
    create.mutate(toPayload(draft), {
      onSuccess: () => {
        setDraft(emptyDraft());
        onCreated?.();
      },
      onError: (err) =>
        toast.error(t("scheduleForm.createFailedToast"), {
          description: errorMessage(err),
        }),
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
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
                  placeholder="USD"
                />
              </div>
            </div>
          );
        })}
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

      <Button type="submit" disabled={create.isPending} className="w-full">
        {create.isPending ? t("common.saving") : t("scheduleForm.create")}
      </Button>
    </form>
  );
}
