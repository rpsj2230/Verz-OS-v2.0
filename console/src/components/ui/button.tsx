/**
 * A button, in the variants every page is built from: primary, outline, secondary, quiet, danger and
 * link.
 *
 * **Three names carry the meaning and the rest are neighbours.** Primary is the one act a page or a
 * dialog is for, quiet is an action that must not compete with it (Cancel, a row's small act, a
 * toolbar control), and danger is an act that removes or stops something. They are the names the
 * owner's design of record uses (`docs/screens.html`), and they replace shadcn/ui's `default`, `ghost`
 * and `destructive`: a name that says what the button is for survives a restyle, where a name that
 * says how it looks is wrong the day the look changes. `outline` is the bordered neighbour of primary
 * and `secondary` the filled one, `link` an inline act. **No other name is accepted**, and
 * `tests/button-variants.test.tsx` reads every call site in the console to hold it: the type refuses
 * the old names here, and the test refuses a computed one, which a type cannot see through data.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0, through the design spike the owner
 * approved, and changed here in four respects:
 *
 * - **The focus ring is the accent's text colour at full strength, two pixels wide.** shadcn/ui
 *   draws it at half opacity, and a half-opacity ring has no contrast figure anyone can state. The
 *   accent's text colour is measured at 4.5 to 1 against every surface in both themes before it is
 *   served (`brain.locale.accent_set`), so the ring inherits that guarantee. `outline-hidden` rather
 *   than `outline-none`, so Windows' forced colours still draw an outline where a box shadow is
 *   removed.
 * - **The secondary hover names a token.** The copy mixed two shadcn/ui variables in an arbitrary
 *   value; those variable names are not defined here (see `theme/tokens.css` on the second
 *   vocabulary), so it would have mixed nothing.
 * - **A link is drawn in the accent's text colour, not its fill.** shadcn/ui writes `text-primary`,
 *   which is the company's colour as configured, and a pale company colour as text on a white page
 *   is unreadable. `text-acc-text` is the same hue moved until it reads.
 * - **The small sizes use the radius scale** rather than `min(var(--radius-md), 8px)`, which comes
 *   to the same value at this console's radius and names a variable Tailwind does not emit.
 *
 * Task ids: M27.10.2, M27.15.71
 */

import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-md border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-hidden select-none focus-visible:ring-2 focus-visible:ring-ring active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground hover:bg-primary/85",
        outline:
          "border-border bg-background shadow-xs hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-line aria-expanded:bg-line",
        quiet: "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground",
        danger: "bg-crit-wash text-destructive hover:bg-crit-wash/70",
        link: "text-acc-text underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-md px-2 text-xs has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1 rounded-md px-2.5 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5",
        lg: "h-10 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-9",
        "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8 rounded-md",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

/**
 * The names a button may be given, in the order a page reaches for them. `tests/button-variants.test.tsx`
 * holds every call site in the console to this list, and `ButtonVariant` is the type a wrapper that
 * passes one through (the dialogs' action and cancel buttons) is written against.
 */
export const BUTTON_VARIANTS = ["primary", "outline", "secondary", "quiet", "danger", "link"] as const;
export type ButtonVariant = (typeof BUTTON_VARIANTS)[number];

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    /** Render the one child as the button, for a router link that must look like one. */
    asChild?: boolean;
  };

function Button({ className, variant = "primary", size = "default", asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
