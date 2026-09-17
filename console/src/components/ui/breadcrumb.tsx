/**
 * Breadcrumbs: where this page sits, as links back up the way.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, and changed:
 *
 * - **The navigation is labelled in the page's language**, "Breadcrumb" with a capital, which is
 *   what a screen reader lists among the landmarks.
 * - **The current page is plain text marked `aria-current`, not a disabled link.** shadcn/ui gives
 *   it `role="link"` and `aria-disabled`, which announces a link that does nothing; the page a person
 *   is on is not a link to anywhere.
 * - **The trail wraps and a long name breaks inside itself**, so an entity name with no space in it
 *   cannot push the page past a phone's edge. `tests/ui-structure.test.tsx` reads the rule at a
 *   phone's width.
 *
 * The trail comes from the route table, never typed per page (5.1). A link here is a router link
 * passed through `asChild`, so the address is the router's and not a second copy of it.
 *
 * Task ids: M27.10.2
 */

import { ChevronRightIcon, MoreHorizontalIcon } from "lucide-react";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Breadcrumb({ className, ...props }: ComponentProps<"nav">) {
  return <nav aria-label="Breadcrumb" data-slot="breadcrumb" className={cn(className)} {...props} />;
}

function BreadcrumbList({ className, ...props }: ComponentProps<"ol">) {
  return (
    <ol
      data-slot="breadcrumb-list"
      className={cn("flex flex-wrap items-center gap-1.5 text-sm [overflow-wrap:anywhere] text-muted-foreground sm:gap-2.5", className)}
      {...props}
    />
  );
}

function BreadcrumbItem({ className, ...props }: ComponentProps<"li">) {
  return <li data-slot="breadcrumb-item" className={cn("inline-flex min-w-0 items-center gap-1.5", className)} {...props} />;
}

function BreadcrumbLink({ asChild, className, ...props }: ComponentProps<"a"> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "a";
  return (
    <Comp
      data-slot="breadcrumb-link"
      className={cn("rounded-sm transition-colors outline-hidden hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring", className)}
      {...props}
    />
  );
}

function BreadcrumbPage({ className, ...props }: ComponentProps<"span">) {
  return <span data-slot="breadcrumb-page" aria-current="page" className={cn("font-normal text-foreground", className)} {...props} />;
}

function BreadcrumbSeparator({ children, className, ...props }: ComponentProps<"li">) {
  return (
    <li data-slot="breadcrumb-separator" role="presentation" aria-hidden="true" className={cn("[&>svg]:size-3.5", className)} {...props}>
      {children ?? <ChevronRightIcon />}
    </li>
  );
}

function BreadcrumbEllipsis({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      data-slot="breadcrumb-ellipsis"
      role="presentation"
      aria-hidden="true"
      className={cn("flex size-5 items-center justify-center [&>svg]:size-4", className)}
      {...props}
    >
      <MoreHorizontalIcon />
      <span className="sr-only">More</span>
    </span>
  );
}

export { Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbLink, BreadcrumbPage, BreadcrumbSeparator, BreadcrumbEllipsis };
