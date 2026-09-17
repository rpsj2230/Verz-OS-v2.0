/**
 * A modal dialog: focus held inside while it is open, Escape closes it, and focus goes back to
 * whatever opened it.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, and changed:
 *
 * - **Focus returns to the opener however the dialog was opened.** See `focus-return.ts`: Radix
 *   returns focus to a `Trigger`, and a dialog opened from state has none. `returnFocusTo` names
 *   the element when the opener will be gone by then.
 * - **The scrim is the design's token.** shadcn/ui paints the overlay a tenth of black, one of the
 *   three colour literals the spike found in the generated components, and in the dark theme a tenth
 *   of black over a near-black page is no scrim at all.
 * - **The title and description set their own margin and size**, because the old stylesheet's
 *   rules for `h2` and `p` sit in the `legacy` layer and still reach an element inside a new
 *   component for every property the component leaves unset, until `styles/app.css` leaves.
 *
 * Task ids: M27.10.2
 */

import { XIcon } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";
import { Button } from "./button";
import { useFocusReturn, type FocusReturnProps } from "./focus-return";

function Dialog(props: ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />;
}

function DialogTrigger(props: ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

function DialogPortal(props: ComponentProps<typeof DialogPrimitive.Portal>) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />;
}

function DialogClose(props: ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

function DialogOverlay({ className, ...props }: ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 isolate z-50 bg-scrim duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0",
        className,
      )}
      {...props}
    />
  );
}

type DialogContentProps = Omit<ComponentProps<typeof DialogPrimitive.Content>, "onOpenAutoFocus" | "onCloseAutoFocus"> &
  FocusReturnProps & {
    showCloseButton?: boolean;
  };

function DialogContent({
  className,
  children,
  showCloseButton = true,
  returnFocusTo,
  onOpenAutoFocus,
  onCloseAutoFocus,
  ...props
}: DialogContentProps) {
  const focus = useFocusReturn({ returnFocusTo, onOpenAutoFocus, onCloseAutoFocus });
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        data-slot="dialog-content"
        onOpenAutoFocus={focus.onOpenAutoFocus}
        onCloseAutoFocus={focus.onCloseAutoFocus}
        className={cn(
          "fixed top-1/2 left-1/2 z-50 [display:grid] w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 gap-6 rounded-xl bg-popover p-6 text-sm text-popover-foreground ring-1 ring-foreground/10 duration-100 outline-hidden sm:max-w-md data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
          className,
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <DialogPrimitive.Close data-slot="dialog-close" asChild>
            <Button variant="ghost" className="absolute top-4 right-4" size="icon-sm">
              <XIcon aria-hidden="true" />
              <span className="sr-only">Close</span>
            </Button>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPortal>
  );
}

function DialogHeader({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="dialog-header" className={cn("flex flex-col gap-2", className)} {...props} />;
}

function DialogFooter({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="dialog-footer" className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)} {...props} />;
}

function DialogTitle({ className, ...props }: ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("m-0 font-heading text-sm leading-none font-medium text-foreground", className)}
      {...props}
    />
  );
}

function DialogDescription({ className, ...props }: ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("m-0 text-sm text-muted-foreground *:[a]:underline *:[a]:underline-offset-3 *:[a]:hover:text-foreground", className)}
      {...props}
    />
  );
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
};
