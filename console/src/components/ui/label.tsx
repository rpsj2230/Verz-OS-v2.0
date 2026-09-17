/**
 * A form label, on Radix's label so a click on it focuses its control.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, unchanged but
 * for the spelling of this repository.
 *
 * Task ids: M27.10.2
 */

import { Label as LabelPrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Label({ className, ...props }: ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        "flex items-center gap-2 text-sm leading-none font-medium text-foreground select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Label };
