import { History, Inbox, Repeat, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { LangToggle } from "@/components/lang-toggle";
import { ModeToggle } from "@/components/mode-toggle";
import { SproutMark } from "@/components/logo";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", labelKey: "nav.inbox", icon: Inbox, end: true },
  { to: "/history", labelKey: "nav.history", icon: History, end: false },
  { to: "/schedules", labelKey: "nav.schedules", icon: Repeat, end: false },
  { to: "/settings", labelKey: "nav.settings", icon: Settings, end: false },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen">
      {/*
        The blur/translucent background lives on an absolutely-positioned sibling
        layer, NOT on <header> itself. A `backdrop-filter` on the header would
        establish a containing block for the fixed mobile nav below, pinning its
        `bottom-0` to the header's bottom edge (i.e. the top of the screen)
        instead of the viewport.
      */}
      <header className="sticky top-0 z-40 border-b border-border/60 pt-safe">
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-background/80 backdrop-blur-xl"
        />
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
              "fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-border/60 bg-background/90 px-2 pb-safe pt-1.5 backdrop-blur-xl",
              "md:static md:flex md:items-center md:gap-1 md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none"
            )}
          >
            {NAV.map(({ to, labelKey, icon: Icon, end }) => (
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
                    {t(labelKey)}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center">
            <LangToggle />
            <ModeToggle />
          </div>
        </div>
      </header>

      <main className="container animate-fade-up py-6 pb-28 md:py-10 md:pb-16">
        {children}
      </main>
    </div>
  );
}
