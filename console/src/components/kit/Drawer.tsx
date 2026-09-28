/**
 * A drawer: a short create or edit that keeps the list behind it in view.
 *
 * `ui/sheet.tsx` with the frame every module's drawer has: a title, a sentence under it, a body that
 * scrolls on its own when it is taller than the screen, and a footer holding the act and the way out.
 * Focus goes back to whatever opened it, which `ui/focus-return.ts` decides for every dialog, and to
 * `returnFocusTo` when the opener will not exist by then, such as the item of a menu that closed.
 *
 * **A drawer that removes something still confirms through `ConfirmDialog` or `ConfirmAction`.**
 * `tests/destructive-confirmed.test.ts` reads every write out of the source and follows it to the
 * control that sends it, and a drawer's submit is not a confirmation.
 *
 * Task ids: M27.10.2
 */

import type { ReactNode } from "react";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "../ui/sheet";

export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  returnFocusTo,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly title: string;
  /** One sentence saying what the drawer changes. */
  readonly description: string;
  readonly children: ReactNode;
  /** The act and the way out. */
  readonly footer?: ReactNode | undefined;
  readonly returnFocusTo?: HTMLElement | null | undefined;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-slot="drawer" returnFocusTo={returnFocusTo} className="gap-0">
        <SheetHeader className="border-b border-line pr-12">
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">{children}</div>
        {footer === undefined ? null : (
          <SheetFooter className="flex-row flex-wrap justify-end gap-2 border-t border-line">{footer}</SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  );
}
