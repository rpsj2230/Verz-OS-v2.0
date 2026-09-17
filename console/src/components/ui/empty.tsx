/**
 * An empty state: a title, a sentence, and what a person can do next.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, with the title
 * a real heading whose level the page chooses, and the stray margins set as `dialog.tsx` explains.
 *
 * **What an empty state says is the hard part and it is not in this file.** 5.2 of the console plan
 * asks it to say what would put a row here and who may, and rule R1 bounds that: "no results" must
 * read the same to a person with nothing to see and a person with nothing they may see. So this
 * component takes its sentence from the page, which takes it from the served constants the four
 * screen-state sentences come from (`tests/screen-states.test.tsx`), and adds nothing of its own:
 * no icon that differs by reason, no count, no "you may not have access".
 *
 * Task ids: M27.10.2
 */

import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Empty({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="empty"
      className={cn(
        "flex w-full min-w-0 flex-1 flex-col items-center justify-center gap-4 rounded-lg border-dashed p-12 text-center text-balance",
        className,
      )}
      {...props}
    />
  );
}

function EmptyHeader({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="empty-header" className={cn("flex max-w-sm flex-col items-center gap-2", className)} {...props} />;
}

const emptyMediaVariants = cva("mb-2 flex shrink-0 items-center justify-center [&_svg]:pointer-events-none [&_svg]:shrink-0", {
  variants: {
    variant: {
      default: "bg-transparent",
      icon: "flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground [&_svg:not([class*='size-'])]:size-6",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

function EmptyMedia({ className, variant = "default", ...props }: ComponentProps<"div"> & VariantProps<typeof emptyMediaVariants>) {
  return <div data-slot="empty-icon" data-variant={variant} aria-hidden="true" className={cn(emptyMediaVariants({ variant, className }))} {...props} />;
}

type HeadingLevel = "h2" | "h3" | "h4";

function EmptyTitle({ className, as: Heading = "h2", ...props }: ComponentProps<"h2"> & { as?: HeadingLevel }) {
  return (
    <Heading
      data-slot="empty-title"
      className={cn("m-0 font-heading text-lg leading-snug font-medium tracking-tight text-foreground", className)}
      {...props}
    />
  );
}

function EmptyDescription({ className, ...props }: ComponentProps<"p">) {
  return (
    <p
      data-slot="empty-description"
      className={cn(
        "m-0 text-sm/relaxed text-muted-foreground [&>a]:text-acc-text [&>a]:underline [&>a]:underline-offset-4",
        className,
      )}
      {...props}
    />
  );
}

function EmptyContent({ className, ...props }: ComponentProps<"div">) {
  return (
    <div data-slot="empty-content" className={cn("flex w-full max-w-sm min-w-0 flex-col items-center gap-4 text-sm text-balance", className)} {...props} />
  );
}

export { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent, EmptyMedia };
