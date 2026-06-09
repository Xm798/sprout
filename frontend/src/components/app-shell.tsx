import { Inbox, Repeat, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";

import { ModeToggle } from "@/components/mode-toggle";
import { SproutMark } from "@/components/logo";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Inbox", icon: Inbox, end: true },
  { to: "/schedules", label: "Schedules", icon: Repeat, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <div className="container flex h-16 items-center justify-between gap-4">
          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary/10 text-primary shadow-soft">
              <SproutMark className="h-5 w-5" />
            </span>
            <span className="font-display text-xl font-semibold tracking-tight">
              Sprout
            </span>
          </NavLink>

          {/* One nav: a horizontal bar on desktop, a fixed tab bar on mobile. */}
          <nav
            className={cn(
              "fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-border/60 bg-background/90 px-2 pb-safe pt-1.5 backdrop-blur-xl",
              "md:static md:flex md:items-center md:gap-1 md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none"
            )}
          >
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "group flex flex-col items-center gap-1 rounded-lg px-3 py-1.5 text-[0.7rem] font-medium text-muted-foreground transition-colors",
                    "md:flex-row md:gap-2 md:px-3.5 md:py-2 md:text-sm",
                    "hover:text-foreground",
                    isActive &&
                      "text-primary md:bg-primary/10 md:text-primary"
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={cn(
                        "grid h-6 w-6 place-items-center transition-transform md:h-auto md:w-auto",
                        isActive && "scale-110 md:scale-100"
                      )}
                    >
                      <Icon className="h-[1.15rem] w-[1.15rem] md:h-4 md:w-4" />
                    </span>
                    {label}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <ModeToggle />
        </div>
      </header>

      <main className="container animate-fade-up py-6 pb-28 md:py-10 md:pb-16">
        {children}
      </main>
    </div>
  );
}
