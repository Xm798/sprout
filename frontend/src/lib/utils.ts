import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function formatDate(value: string) {
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatAmount(amount: string | number, currency?: string) {
  const n = typeof amount === "number" ? amount : Number(amount);
  if (Number.isNaN(n)) return `${amount}${currency ? ` ${currency}` : ""}`;
  const body = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
  return currency ? `${body} ${currency}` : body;
}

// Convert percent string to decimal string, e.g. "4.85" -> "0.0485".
// Uses toFixed(10) to avoid floating-point noise, then strips trailing zeros.
export function percentToDecimal(pct: string): string {
  const num = parseFloat(pct);
  if (isNaN(num)) return "0";
  return String(parseFloat((num / 100).toFixed(10)));
}

/** Last segment of a Beancount account, for compact display. */
export function leafAccount(account?: string) {
  if (!account) return "—";
  const parts = account.split(":");
  return parts[parts.length - 1] || account;
}
