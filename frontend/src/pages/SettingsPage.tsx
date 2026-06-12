import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Save } from "lucide-react";
import { toast } from "sonner";

import { useConfig, useCurrencies, useUpdateConfig } from "@/api/hooks";
import type { AppConfig } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

export function SettingsPage() {
  const config = useConfig();
  const currencies = useCurrencies();
  const update = useUpdateConfig();
  const [form, setForm] = useState<AppConfig | null>(null);

  useEffect(() => {
    if (config.data) setForm(config.data);
  }, [config.data]);

  function set<K extends keyof AppConfig>(key: K, value: AppConfig[K]) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (form)
      update.mutate(form, {
        onSuccess: () => toast.success("Settings saved"),
        onError: (err) =>
          toast.error("Couldn't save", { description: String(err) }),
      });
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header className="space-y-1">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Settings
        </h1>
        <p className="text-sm text-muted-foreground">
          Where and how Sprout writes Beancount transactions.
        </p>
      </header>

      {!form ? (
        <Skeleton className="h-96 w-full rounded-lg" />
      ) : (
        <form onSubmit={submit} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Ledger</CardTitle>
              <CardDescription>
                Paths Sprout reads from and writes into.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field
                id="ledger_main_file"
                label="Ledger main file"
                value={form.ledger_main_file}
                onChange={(v) => set("ledger_main_file", v)}
              />
              <Field
                id="ledger_root"
                label="Ledger root"
                value={form.ledger_root}
                onChange={(v) => set("ledger_root", v)}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Write mode</CardTitle>
              <CardDescription>
                How confirmed transactions are organized on disk.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="write_mode">Mode</Label>
                <Select
                  value={form.write_mode}
                  onValueChange={(v) => set("write_mode", v)}
                >
                  <SelectTrigger id="write_mode" aria-label="write mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="single_file">Single file</SelectItem>
                    <SelectItem value="month_file">
                      Monthly files
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Field
                id="single_file_name"
                label="Single file name"
                value={form.single_file_name}
                onChange={(v) => set("single_file_name", v)}
              />
              <Field
                id="month_file_template"
                label="Month file template"
                value={form.month_file_template}
                onChange={(v) => set("month_file_template", v)}
                mono
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Defaults</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field
                id="default_tag"
                label="Default tag"
                value={form.default_tag}
                onChange={(v) => set("default_tag", v)}
              />
              <div className="space-y-1.5">
                <Label htmlFor="default_currency">Default currency</Label>
                <Combobox
                  id="default_currency"
                  value={form.default_currency}
                  onChange={(v) => set("default_currency", v)}
                  suggestions={currencies.data ?? []}
                  transform={(v) => v.toUpperCase()}
                  placeholder="USD"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lookahead_days">Lookahead days</Label>
                <Input
                  id="lookahead_days"
                  type="number"
                  value={form.lookahead_days}
                  onChange={(e) =>
                    set("lookahead_days", Number(e.target.value))
                  }
                />
              </div>
            </CardContent>
          </Card>

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={update.isPending}>
              <Save className="h-4 w-4" />
              {update.isPending ? "Saving…" : "Save"}
            </Button>
            {update.isSuccess && (
              <span className="text-sm text-success">Saved</span>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  mono,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  mono?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={mono ? "font-mono text-xs" : undefined}
      />
    </div>
  );
}
