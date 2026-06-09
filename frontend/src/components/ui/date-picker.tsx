import { useState } from "react";
import { format, parseISO } from "date-fns";
import { CalendarIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

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
  placeholder = "Pick a date",
  ...rest
}: DatePickerProps) {
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
          {selected ? format(selected, "PPP") : placeholder}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
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
            Today
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
              Clear
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
