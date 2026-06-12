import { useState } from "react";
import type { Locale } from "date-fns";
import { format, parseISO } from "date-fns";
import { enUS, zhCN } from "date-fns/locale";
import { CalendarIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const DATE_LOCALES: Record<string, Locale> = { en: enUS, "zh-CN": zhCN };

interface DatePickerProps {
  /** ISO date string, e.g. "2026-01-15", or "" when unset. */
  value: string;
  onChange: (value: string) => void;
  id?: string;
  placeholder?: string;
  "aria-label"?: string;
}

export function DatePicker({
  value,
  onChange,
  id,
  placeholder,
  ...rest
}: DatePickerProps) {
  const { t, i18n } = useTranslation();
  const locale = DATE_LOCALES[i18n.resolvedLanguage ?? "en"] ?? enUS;
  const [open, setOpen] = useState(false);
  const selected = value ? parseISO(value) : undefined;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          aria-label={rest["aria-label"]}
          className={cn(
            "w-full justify-start font-normal",
            !value && "text-muted-foreground"
          )}
        >
          <CalendarIcon className="h-4 w-4 opacity-70" />
          {selected
            ? format(selected, "PPP", { locale })
            : (placeholder ?? t("datePicker.pickDate"))}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          locale={locale}
          onSelect={(d) => {
            onChange(d ? format(d, "yyyy-MM-dd") : "");
            setOpen(false);
          }}
          initialFocus
        />
        <div className="flex items-center justify-between border-t border-border/60 p-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              onChange(format(new Date(), "yyyy-MM-dd"));
              setOpen(false);
            }}
          >
            {t("datePicker.today")}
          </Button>
          {value && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-muted-foreground"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
            >
              {t("datePicker.clear")}
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
