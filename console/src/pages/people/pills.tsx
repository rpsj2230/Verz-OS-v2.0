/**
 * A person's standing and whether their last sign-in carried a second factor, as the design of
 * record's `.pill` draws a state: the word carries the meaning and the colour repeats it.
 *
 * Task ids: M27.16.1
 */

import { STAFF_STATUS_WORDS } from "./peopleQuery";
import { cn } from "../../lib/utils";

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em] whitespace-nowrap";

export function StandingPill({ standing }: { readonly standing: "live" | "disabled" }) {
  return (
    <span data-slot="standing-pill" className={cn(PILL, standing === "disabled" ? "bg-crit-wash text-crit" : "bg-ok-wash text-ok")}>
      {standing === "disabled" ? "Disabled" : "Live"}
    </span>
  );
}

export function SecondFactorPill({ seen }: { readonly seen: boolean }) {
  return (
    <span data-slot="second-factor-pill" className={cn(PILL, seen ? "bg-ok-wash text-ok" : "bg-warn-wash text-warn")}>
      {seen ? "Seen" : "Not seen"}
    </span>
  );
}

/** A small plain pill, for a kind of thing rather than a state. */
export function KindPill({ children }: { readonly children: string }) {
  return <span className={cn(PILL, "bg-sunk text-body")}>{children}</span>;
}

/** Where the staff list says somebody stands. Anything but active is why they cannot sign in. */
export function StaffStatusPill({ status }: { readonly status: string }) {
  return (
    <span data-slot="staff-status-pill" className={cn(PILL, status === "active" ? "bg-ok-wash text-ok" : "bg-warn-wash text-warn")}>
      {STAFF_STATUS_WORDS[status] ?? status}
    </span>
  );
}
