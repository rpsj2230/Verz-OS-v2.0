/**
 * A single-line text input, and a multi-line one beside it in `textarea.tsx`.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, with the focus
 * ring changed as `button.tsx` explains and the placeholder in the muted text colour, which is
 * measured against every surface (`brain.locale.READ_PAIRS`).
 *
 * **A password field is not a variant of this.** `scripts/check-boundaries.mjs` refuses a password
 * input anywhere in the console, and a credential is typed into `secret-field.tsx`, which is written
 * so that its value is never read back into the page.
 *
 * Task ids: M27.10.2
 */

import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Input({ className, type, ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2.5 py-1 text-base text-foreground shadow-xs transition-[color,box-shadow] outline-hidden file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive md:text-sm",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
