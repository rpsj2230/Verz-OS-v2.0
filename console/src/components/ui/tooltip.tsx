/**
 * A tooltip: a short label shown on hover and on keyboard focus of its trigger, and dismissed by
 * Escape.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike. The tooltip is
 * the ink colour with the ground's colour for text, which is the design's highest-contrast pair.
 *
 * **A tooltip never carries the only statement of something.** It is not reachable on a touch
 * screen and it is read inconsistently by screen readers, so a reason, a warning or a value that
 * matters is written on the page. And **a tooltip never explains a refusal**: "restricted because
 * out of scope" on a lock is the disclosure `ui/Lock.tsx` takes no props to prevent, and a tooltip
 * is exactly where somebody being helpful would put it. `tests/lock.test.tsx` holds the lock.
 *
 * The delay is Radix's own seven hundred milliseconds rather than shadcn/ui's zero, so moving a
 * pointer across a toolbar does not flash a label over every control it crosses.
 *
 * Task ids: M27.10.2
 */

import { Tooltip as TooltipPrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function TooltipProvider(props: ComponentProps<typeof TooltipPrimitive.Provider>) {
  return <TooltipPrimitive.Provider data-slot="tooltip-provider" {...props} />;
}

function Tooltip(props: ComponentProps<typeof TooltipPrimitive.Root>) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />;
}

function TooltipTrigger(props: ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

function TooltipContent({ className, sideOffset = 4, children, ...props }: ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "z-50 inline-flex w-fit max-w-xs origin-(--radix-tooltip-content-transform-origin) items-center gap-1.5 rounded-md bg-foreground px-3 py-1.5 text-xs text-background data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0 data-[state=delayed-open]:zoom-in-95 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
          className,
        )}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow className="z-50 size-2.5 translate-y-[calc(-50%_-_2px)] rotate-45 rounded-[2px] bg-foreground fill-foreground" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
