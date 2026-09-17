/**
 * A multi-line text input. See `input.tsx`; the changes from shadcn/ui are the same.
 *
 * Task ids: M27.10.2
 */

import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-md border border-input bg-transparent px-2.5 py-2 text-base text-foreground shadow-xs transition-[color,box-shadow] outline-hidden placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive md:text-sm",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
