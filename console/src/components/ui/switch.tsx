/**
 * An on and off switch, announced as a switch.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, with the focus
 * ring changed as `button.tsx` explains. The thumb is the panel colour on the accent fill when on,
 * and the unchecked track is the line colour.
 *
 * **A switch is for a setting that takes effect at once.** A switch that stages a change for a Save
 * button elsewhere reads as done when it is not; that is the page's to get right, and the note is
 * here because this is the file somebody opens when choosing between this and a checkbox.
 *
 * Task ids: M27.10.2
 */

import { Switch as SwitchPrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Switch({
  className,
  size = "default",
  ...props
}: ComponentProps<typeof SwitchPrimitive.Root> & { size?: "sm" | "default" }) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        "peer group/switch relative inline-flex shrink-0 items-center rounded-full border border-transparent shadow-xs transition-all outline-hidden after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:ring-2 focus-visible:ring-ring aria-invalid:border-destructive data-[size=default]:h-[18.4px] data-[size=default]:w-[32px] data-[size=sm]:h-[14px] data-[size=sm]:w-[24px] data-checked:bg-primary data-unchecked:bg-input data-disabled:cursor-not-allowed data-disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block rounded-full bg-background ring-0 transition-transform group-data-[size=default]/switch:size-4 group-data-[size=sm]/switch:size-3 group-data-[size=default]/switch:data-checked:translate-x-[calc(100%-2px)] group-data-[size=sm]/switch:data-checked:translate-x-[calc(100%-2px)] data-checked:bg-primary-foreground group-data-[size=default]/switch:data-unchecked:translate-x-0 group-data-[size=sm]/switch:data-unchecked:translate-x-0 dark:data-unchecked:bg-foreground"
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
