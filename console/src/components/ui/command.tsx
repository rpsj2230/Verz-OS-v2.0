/**
 * A command palette: a search box over a list moved through with the arrow keys, alone or in a
 * dialog opened from anywhere. The part global search is built from (W1.5).
 *
 * shadcn/ui's wrapper around `cmdk`, copied through the design spike and changed:
 *
 * - **The input stands alone** rather than inside shadcn/ui's input group, which is one more copied
 *   component for one icon beside a field.
 * - **The dialog returns focus to what opened it**, which for a palette opened by a key is whatever
 *   had focus when the key was pressed (see `focus-return.ts`).
 * - **The dialog is titled in the page's language**, for a screen reader, and the title is not
 *   shown.
 *
 * **What the palette must never say is a number, and what it must never do is filter a list it was
 * handed.** cmdk filters and sorts the items it is given, which is right for the menu entries a
 * reader already has and wrong for anything a server searched: the server's answer is the answer,
 * and `GET /api/v1/console/search` returns the same empty answer for "no match" and "not permitted"
 * (5.1). So a server-backed palette passes `shouldFilter={false}`, and nothing here renders a count
 * of results, of groups or of anything hidden. `tests/ui-rules.test.ts` holds the second half over
 * every component in this directory.
 *
 * Task ids: M27.10.2
 */

import { Command as CommandPrimitive } from "cmdk";
import { SearchIcon } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./dialog";
import type { FocusReturnProps } from "./focus-return";

function Command({ className, ...props }: ComponentProps<typeof CommandPrimitive>) {
  return (
    <CommandPrimitive
      data-slot="command"
      className={cn("flex size-full flex-col overflow-hidden rounded-xl bg-popover p-1 text-popover-foreground", className)}
      {...props}
    />
  );
}

type CommandDialogProps = ComponentProps<typeof Dialog> &
  Pick<FocusReturnProps, "returnFocusTo"> & {
    title?: string;
    description?: string;
    className?: string;
    /** False when the items are a server's answer, which is already the answer (see above). */
    shouldFilter?: boolean;
  };

function CommandDialog({
  title = "Search the console",
  description = "Type to search, move with the arrow keys and press Enter to open.",
  children,
  className,
  returnFocusTo,
  shouldFilter = true,
  ...props
}: CommandDialogProps) {
  return (
    <Dialog {...props}>
      <DialogContent
        className={cn("top-1/3 translate-y-0 overflow-hidden rounded-xl p-0", className)}
        showCloseButton={false}
        returnFocusTo={returnFocusTo}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <Command shouldFilter={shouldFilter}>{children}</Command>
      </DialogContent>
    </Dialog>
  );
}

function CommandInput({ className, ...props }: ComponentProps<typeof CommandPrimitive.Input>) {
  return (
    <div data-slot="command-input-wrapper" className="flex h-9 items-center gap-2 border-b border-border px-3">
      <SearchIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <CommandPrimitive.Input
        data-slot="command-input"
        className={cn(
          "flex h-10 w-full min-w-0 bg-transparent py-2 text-sm text-foreground outline-hidden placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
    </div>
  );
}

function CommandList({ className, ...props }: ComponentProps<typeof CommandPrimitive.List>) {
  return (
    <CommandPrimitive.List
      data-slot="command-list"
      className={cn("no-scrollbar max-h-72 scroll-py-1 overflow-x-hidden overflow-y-auto outline-hidden", className)}
      {...props}
    />
  );
}

function CommandEmpty({ className, ...props }: ComponentProps<typeof CommandPrimitive.Empty>) {
  return <CommandPrimitive.Empty data-slot="command-empty" className={cn("py-6 text-center text-sm text-muted-foreground", className)} {...props} />;
}

function CommandGroup({ className, ...props }: ComponentProps<typeof CommandPrimitive.Group>) {
  return (
    <CommandPrimitive.Group
      data-slot="command-group"
      className={cn(
        "overflow-hidden p-1 text-foreground **:[[cmdk-group-heading]]:px-2 **:[[cmdk-group-heading]]:py-1.5 **:[[cmdk-group-heading]]:text-xs **:[[cmdk-group-heading]]:font-medium **:[[cmdk-group-heading]]:text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

function CommandSeparator({ className, ...props }: ComponentProps<typeof CommandPrimitive.Separator>) {
  return <CommandPrimitive.Separator data-slot="command-separator" className={cn("-mx-1 h-px w-auto bg-border", className)} {...props} />;
}

function CommandItem({ className, ...props }: ComponentProps<typeof CommandPrimitive.Item>) {
  return (
    <CommandPrimitive.Item
      data-slot="command-item"
      className={cn(
        "relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-hidden select-none data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50 data-selected:bg-accent data-selected:text-accent-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  );
}

function CommandShortcut({ className, ...props }: ComponentProps<"span">) {
  return <span data-slot="command-shortcut" className={cn("ml-auto text-xs tracking-widest text-muted-foreground", className)} {...props} />;
}

export { Command, CommandDialog, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem, CommandShortcut, CommandSeparator };
