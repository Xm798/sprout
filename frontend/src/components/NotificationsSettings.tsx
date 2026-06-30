import { useEffect, useState } from "react";
import { Save, TestTube2, Trash2, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import {
  useNotifications,
  useUpdateNotifications,
  useTestNotification,
} from "../api/hooks";
import type { NotificationChannel, NotificationSettings } from "../api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function NotificationsSettings() {
  const { t } = useTranslation();
  const { data } = useNotifications();
  const update = useUpdateNotifications();
  const test = useTestNotification();
  const [form, setForm] = useState<NotificationSettings | null>(null);

  // Seed local state once from the query; edits are local until Save.
  useEffect(() => {
    if (data && !form) setForm(data);
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!form) return null;

  const setChannel = (i: number, patch: Partial<NotificationChannel>) =>
    setForm({
      ...form,
      notify_channels: form.notify_channels.map((c, j) =>
        j === i ? { ...c, ...patch } : c
      ),
    });

  const addChannel = () =>
    setForm({
      ...form,
      notify_channels: [...form.notify_channels, { name: "", url: "", enabled: true }],
    });

  const removeChannel = (i: number) =>
    setForm({
      ...form,
      notify_channels: form.notify_channels.filter((_, j) => j !== i),
    });

  const save = async () => {
    try {
      await update.mutateAsync(form);
      toast.success(t("notify.saved"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };

  const runTest = async (name?: string) => {
    try {
      const res = await test.mutateAsync(name);
      const lines = Object.entries(res as Record<string, unknown>).map(
        ([n, v]) => `${n}: ${v === true ? "✅" : String(v)}`
      );
      toast(lines.join("\n"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("notify.title")}</CardTitle>
        <CardDescription>{t("notify.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Enable toggle */}
        <div className="flex items-center gap-2">
          <input
            id="notify_enabled"
            type="checkbox"
            className="h-4 w-4 rounded border-border accent-primary"
            checked={form.notify_enabled}
            onChange={(e) => setForm({ ...form, notify_enabled: e.target.checked })}
          />
          <Label htmlFor="notify_enabled">{t("notify.enabled")}</Label>
        </div>

        {/* Timing fields */}
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="notify_lead_days">{t("notify.leadDays")}</Label>
            <Input
              id="notify_lead_days"
              type="number"
              min={0}
              value={form.notify_lead_days}
              onChange={(e) =>
                setForm({ ...form, notify_lead_days: Number(e.target.value) })
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="notify_time">{t("notify.time")}</Label>
            <Input
              id="notify_time"
              type="time"
              value={form.notify_time}
              onChange={(e) => setForm({ ...form, notify_time: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="notify_timezone">{t("notify.timezone")}</Label>
            <Input
              id="notify_timezone"
              value={form.notify_timezone}
              placeholder="UTC"
              onChange={(e) =>
                setForm({ ...form, notify_timezone: e.target.value })
              }
            />
          </div>
        </div>

        {/* Channel list */}
        <div className="space-y-2">
          {form.notify_channels.map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input
                className="w-32 shrink-0"
                placeholder={t("notify.channelName")}
                value={c.name}
                onChange={(e) => setChannel(i, { name: e.target.value })}
              />
              <Input
                className="flex-1"
                placeholder={t("notify.appriseUrl")}
                value={c.url}
                onChange={(e) => setChannel(i, { url: e.target.value })}
              />
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-border accent-primary"
                checked={c.enabled}
                onChange={(e) => setChannel(i, { enabled: e.target.checked })}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => runTest(c.name)}
              >
                <TestTube2 className="h-4 w-4" />
                {t("notify.test")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeChannel(i)}
                aria-label={`Remove channel ${i + 1}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}

          <Button type="button" variant="outline" size="sm" onClick={addChannel}>
            <Plus className="h-4 w-4" />
            {t("notify.addChannel")}
          </Button>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pt-2">
          <Button type="button" onClick={save} disabled={update.isPending}>
            <Save className="h-4 w-4" />
            {update.isPending ? t("common.saving") : t("common.save")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => runTest()}
          >
            <TestTube2 className="h-4 w-4" />
            {t("notify.testAll")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
