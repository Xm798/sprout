import { ArrowRight } from "lucide-react";

import type { FlowLeg, PostingFlow } from "@/api/postings";
import { useMediaQuery } from "@/hooks/use-media-query";
import { leafAccount } from "@/lib/utils";

function Side({
  legs,
  cap,
  leafNames,
}: {
  legs: FlowLeg[];
  cap: number;
  leafNames: boolean;
}) {
  const shown = legs.slice(0, cap);
  const hidden = legs.slice(cap);
  const label = (account: string) => (leafNames ? leafAccount(account) : account);
  const hiddenNames = hidden.map((l) => l.posting.account).join(", ");
  return (
    <>
      <span className="min-w-0 truncate">
        {shown.length > 0
          ? shown.map((l) => label(l.posting.account)).join(" · ")
          : "—"}
      </span>
      {hidden.length > 0 && (
        // title is hover-only; aria-label carries the same info for keyboard/SR.
        <span
          className="shrink-0 rounded-full bg-muted px-1.5 py-px text-[10px] font-medium text-muted-foreground"
          title={hiddenNames}
          aria-label={`+${hidden.length} more: ${hiddenNames}`}
        >
          +{hidden.length}
        </span>
      )}
    </>
  );
}

/** "sources → destinations" account line for a posting flow. Caps visible
 *  accounts per side (1 below 640px, else 2); the rest fold into a +N badge. */
export function FlowAccounts({
  flow,
  leafNames = true,
}: {
  flow: PostingFlow;
  leafNames?: boolean;
}) {
  const wide = useMediaQuery("(min-width: 640px)");
  const cap = wide ? 2 : 1;
  return (
    <>
      <Side legs={flow.sources} cap={cap} leafNames={leafNames} />
      <ArrowRight className="h-3.5 w-3.5 shrink-0 opacity-70" />
      <Side legs={flow.destinations} cap={cap} leafNames={leafNames} />
    </>
  );
}
