import { useRef, useState } from "react";
import { CalendarPlus, Pencil, Plus, Repeat, Trash2 } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { useDeleteSchedule, useSchedules } from "@/api/hooks";
import { analyzeFlow, headlineDisplay } from "@/api/postings";
import type { Schedule } from "@/api/types";
import { FlowAccounts } from "@/components/FlowAccounts";
import { ScheduleForm } from "@/components/ScheduleForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useMediaQuery } from "@/hooks/use-media-query";
import { formatAmount } from "@/lib/utils";

function intervalLabel(s: Schedule, t: TFunction) {
  return s.interval_count === 1
    ? t(`schedules.everyOne.${s.interval_unit}`)
    : t(`schedules.everyMany.${s.interval_unit}`, {
        count: s.interval_count,
      });
}

function ScheduleCard({
  schedule,
  isDesktop,
}: {
  schedule: Schedule;
  isDesktop: boolean;
}) {
  const { t } = useTranslation();
  const del = useDeleteSchedule();
  const [editOpen, setEditOpen] = useState(false);
  const editTriggerRef = useRef<HTMLButtonElement>(null);
  const flow = analyzeFlow(schedule.postings);
  const { amount, currency } = headlineDisplay(flow, schedule);

  // The edit dialog is controlled without a Radix trigger, so its default
  // close-focus return targets a null ref; restore focus to the pencil
  // button ourselves once the focus trap has been torn down.
  function restoreEditFocus(e: Event) {
    e.preventDefault();
    editTriggerRef.current?.focus();
  }

  const editForm = (
    <ScheduleForm schedule={schedule} onSaved={() => setEditOpen(false)} />
  );

  return (
    <Card className="group transition-shadow hover:shadow-lift">
      <CardContent className="flex items-center justify-between gap-3 p-4 sm:p-5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <Repeat className="h-5 w-5" />
          </span>
          <div className="min-w-0 space-y-1">
            <p className="truncate font-display text-base font-semibold">
              {schedule.name}
            </p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="outline">{intervalLabel(schedule, t)}</Badge>
              <span className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
                <FlowAccounts flow={flow} leafNames={false} />
              </span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <span className="font-mono text-sm font-semibold tabular-nums">
            {amount != null ? formatAmount(amount, currency) : "—"}
          </span>
          <div className="flex items-center gap-0.5">
            <Button
              ref={editTriggerRef}
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground"
              aria-label={t("schedules.editAria", { name: schedule.name })}
              onClick={() => setEditOpen(true)}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
              aria-label={t("schedules.deleteAria", { name: schedule.name })}
              disabled={del.isPending}
              onClick={() =>
                del.mutate(schedule.id, {
                  onSuccess: () => toast(t("schedules.deletedToast", { name: schedule.name })),
                })
              }
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
      {isDesktop ? (
        <Dialog open={editOpen} onOpenChange={setEditOpen}>
          <DialogContent
            className="max-h-[90vh] overflow-y-auto [scrollbar-gutter:stable]"
            onCloseAutoFocus={restoreEditFocus}
          >
            <DialogHeader>
              <DialogTitle>{t("schedules.editSchedule")}</DialogTitle>
              <DialogDescription>
                {t("schedules.editDescription")}
              </DialogDescription>
            </DialogHeader>
            {editForm}
          </DialogContent>
        </Dialog>
      ) : (
        <Sheet open={editOpen} onOpenChange={setEditOpen}>
          <SheetContent
            side="bottom"
            className="max-h-[92vh] overflow-y-auto p-6 pb-8 [scrollbar-gutter:stable]"
            onCloseAutoFocus={restoreEditFocus}
          >
            <SheetHeader className="mb-4 text-left">
              <SheetTitle>{t("schedules.editSchedule")}</SheetTitle>
              <SheetDescription>
                {t("schedules.editDescription")}
              </SheetDescription>
            </SheetHeader>
            {editForm}
          </SheetContent>
        </Sheet>
      )}
    </Card>
  );
}

export function SchedulesPage() {
  const { t } = useTranslation();
  const schedules = useSchedules();
  const [open, setOpen] = useState(false);
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const list = schedules.data ?? [];

  const trigger = (
    <Button>
      <Plus className="h-4 w-4" />
      {t("schedules.newSchedule")}
    </Button>
  );

  const form = <ScheduleForm onSaved={() => setOpen(false)} />;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            {t("schedules.title")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("schedules.subtitle")}
          </p>
        </div>

        {isDesktop ? (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{trigger}</DialogTrigger>
            <DialogContent className="max-h-[90vh] overflow-y-auto [scrollbar-gutter:stable]">
              <DialogHeader>
                <DialogTitle>{t("schedules.newSchedule")}</DialogTitle>
                <DialogDescription>
                  {t("schedules.dialogDescription")}
                </DialogDescription>
              </DialogHeader>
              {form}
            </DialogContent>
          </Dialog>
        ) : (
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>{trigger}</SheetTrigger>
            <SheetContent
              side="bottom"
              className="max-h-[92vh] overflow-y-auto p-6 pb-8 [scrollbar-gutter:stable]"
            >
              <SheetHeader className="mb-4 text-left">
                <SheetTitle>{t("schedules.newSchedule")}</SheetTitle>
                <SheetDescription>
                  {t("schedules.sheetDescription")}
                </SheetDescription>
              </SheetHeader>
              {form}
            </SheetContent>
          </Sheet>
        )}
      </header>

      {schedules.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <Card className="border-dashed bg-card/50">
          <CardContent className="flex flex-col items-center gap-3 px-6 py-14 text-center">
            <span className="grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary">
              <CalendarPlus className="h-7 w-7" />
            </span>
            <div className="space-y-1">
              <p className="font-display text-lg font-semibold">
                {t("schedules.emptyTitle")}
              </p>
              <p className="text-sm text-muted-foreground">
                {t("schedules.emptyBody")}
              </p>
            </div>
            <Button className="mt-1" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" />
              {t("schedules.newSchedule")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {list.map((s, i) => (
            <div
              key={s.id}
              className="animate-fade-up"
              style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
            >
              <ScheduleCard schedule={s} isDesktop={isDesktop} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
