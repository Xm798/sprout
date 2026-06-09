import * as React from "react";
import { Check } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface ComboboxProps {
  value: string;
  onChange: (value: string) => void;
  suggestions: string[];
  id?: string;
  placeholder?: string;
  required?: boolean;
  "aria-label"?: string;
  /** Normalize input as the user types (e.g. uppercase currencies). */
  transform?: (raw: string) => string;
  /** Cap on rendered suggestions. */
  max?: number;
}

/**
 * Free-text autocomplete: a real <input> (labelable, typeable, accepts any
 * value) paired with a styled suggestion list. The list never steals focus —
 * options commit on mousedown — so typing flows uninterrupted.
 */
export function Combobox({
  value,
  onChange,
  suggestions,
  id,
  placeholder,
  required,
  transform,
  max = 8,
  ...rest
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(-1);
  const blurTimer = React.useRef<ReturnType<typeof setTimeout>>();
  const listId = id ? `${id}-listbox` : undefined;

  const needle = value.trim().toLowerCase();
  const matches = suggestions
    .filter((s) => s.toLowerCase().includes(needle))
    .filter((s) => s !== value)
    .slice(0, max);

  const showList = open && matches.length > 0;

  function commit(next: string) {
    onChange(next);
    setOpen(false);
    setActive(-1);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && open && active >= 0 && matches[active]) {
      e.preventDefault();
      commit(matches[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setActive(-1);
    }
  }

  return (
    <div className="relative">
      <Input
        id={id}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        required={required}
        placeholder={placeholder}
        aria-label={rest["aria-label"]}
        value={value}
        onChange={(e) => {
          const raw = e.target.value;
          onChange(transform ? transform(raw) : raw);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          blurTimer.current = setTimeout(() => setOpen(false), 120);
        }}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-50 mt-1.5 max-h-60 w-full overflow-auto rounded-lg border border-border/70 bg-popover p-1 shadow-lift"
          onMouseDown={(e) => {
            // Keep focus on the input so the blur-close timer doesn't fire.
            e.preventDefault();
            clearTimeout(blurTimer.current);
          }}
        >
          {matches.map((s, i) => (
            <li
              key={s}
              role="option"
              aria-selected={i === active}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm",
                i === active
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-accent/60"
              )}
              onMouseEnter={() => setActive(i)}
              onClick={() => commit(s)}
            >
              <Check
                className={cn(
                  "h-3.5 w-3.5 shrink-0",
                  s === value ? "opacity-100" : "opacity-0"
                )}
              />
              <span className="truncate">{s}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
