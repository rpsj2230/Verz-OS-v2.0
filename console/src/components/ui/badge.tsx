/**
 * A short label with a variant, for the design's pills.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, with the focus
 * ring and the link colour changed as `button.tsx` explains.
 *
 * **Not a second status primitive.** `ui/Badge.tsx` is the one place a state word becomes a colour,
 * and `tests/status-primitives.test.tsx` holds that nothing outside `ui/Status.tsx` computes a tone.
 * This badge's `variant` is the same kind of choice spelled differently, so
 * `tests/ui-rules.test.ts` holds it to the same rule: a variant here is a literal at every call
 * site, never a value computed from a row, because a colour chosen from data is how a fact about
 * what somebody may see reaches a screen that somebody else's does not have.
 *
 * Task ids: M27.10.2
 */

import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all outline-hidden focus-visible:ring-2 focus-visible:ring-ring has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/85",
        secondary: "bg-secondary text-secondary-foreground [a]:hover:bg-line",
        destructive: "bg-crit-wash text-destructive [a]:hover:bg-crit-wash/70",
        outline: "border-border text-foreground [a]:hover:bg-muted",
        ghost: "hover:bg-muted",
        link: "text-acc-text underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

type BadgeProps = ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { asChild?: boolean };

function Badge({ className, variant = "default", asChild = false, ...props }: BadgeProps) {
  const Comp = asChild ? Slot.Root : "span";
  return <Comp data-slot="badge" data-variant={variant} className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
