import { cn } from "@/lib/utils";

/** The Sprout mark — a single sprouting seedling, drawn with currentColor. */
export function SproutMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      className={cn("h-full w-full", className)}
      aria-hidden="true"
    >
      <path
        d="M16 28V15.5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M16 16.5C16 12 12.5 8.5 7 8.5c0 5.5 3.5 9 9 9Z"
        fill="currentColor"
        fillOpacity="0.55"
      />
      <path
        d="M16 14.5C16 9.5 19.8 5.5 25.5 5.5c0 5.6-3.8 9.5-9.5 9.5Z"
        fill="currentColor"
      />
    </svg>
  );
}
