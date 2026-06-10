import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
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
