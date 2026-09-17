/**
 * Focus goes back to whatever opened a dialog, a sheet or a confirmation, however it was opened.
 *
 * **Measured, and it is Radix's default that is wrong for this console.** Radix's dialog content,
 * on closing, prevents its own focus scope from restoring focus and focuses the dialog's
 * `Trigger` instead. A dialog opened from state has no `Trigger`: a confirmation opened by a menu
 * item, a sheet opened by a row's button, the command palette opened by a key. In the design spike
 * each of those left focus on `<body>` when it closed, so somebody on a keyboard was put back at
 * the top of the page with no way to tell where they had been. The spike fixed it in its
 * `ConfirmAction`; it is fixed here instead, in the parts every dialog is built from, so a dialog
 * written next month does not have to know.
 *
 * **How.** When the content mounts, before Radix moves focus into it, the element that has focus
 * is the opener, and it is remembered. When the content closes, focus is given back to it, unless
 * the caller named a different element (`returnFocusTo`, for an opener that no longer exists, such
 * as the item of a menu that closed) or handled the event itself. If nothing was remembered, Radix's
 * own behaviour stands.
 *
 * Task ids: M27.10.2
 */

import { useRef } from "react";

export interface FocusReturnProps {
  /** Where focus goes on close, when the element that opened this will not exist by then. */
  readonly returnFocusTo?: HTMLElement | null | undefined;
  readonly onOpenAutoFocus?: ((event: Event) => void) | undefined;
  readonly onCloseAutoFocus?: ((event: Event) => void) | undefined;
}

export function useFocusReturn({ returnFocusTo, onOpenAutoFocus, onCloseAutoFocus }: FocusReturnProps): {
  onOpenAutoFocus: (event: Event) => void;
  onCloseAutoFocus: (event: Event) => void;
} {
  const opener = useRef<HTMLElement | null>(null);
  return {
    onOpenAutoFocus(event) {
      const active = globalThis.document.activeElement;
      opener.current = active instanceof HTMLElement && active !== globalThis.document.body ? active : null;
      onOpenAutoFocus?.(event);
    },
    onCloseAutoFocus(event) {
      onCloseAutoFocus?.(event);
      if (event.defaultPrevented) {
        return;
      }
      const target = returnFocusTo ?? opener.current;
      if (target?.isConnected) {
        event.preventDefault();
        target.focus();
      }
    },
  };
}
