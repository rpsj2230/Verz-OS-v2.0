/**
 * The toast region: where the result of a write is announced, politely, beside the page's own
 * statement of it.
 *
 * shadcn/ui's wrapper around `sonner`, copied through the design spike and changed:
 *
 * - **The theme is the console's three-state preference**, read from `theme/theme.ts`, rather than
 *   `next-themes`, which this console does not have. "system" is passed through as system, so the
 *   toaster follows the machine exactly as `tokens.css` does.
 * - **Every colour is a token.** sonner injects a stylesheet of its own with greys written as
 *   literals, and its description text is one of them; the wrapper points sonner's variables at the
 *   design's panel, ink and line, and marks the description's class important because an injected
 *   stylesheet is unlayered and outranks every utility otherwise.
 * - **The region is labelled in the page's language.**
 *
 * **What a toast may never be** (5.2 of the console plan): the only place a failure is reported, or
 * a place a value appears that is withheld anywhere else. A toast disappears and a screen reader may
 * be mid-sentence when it arrives, so the page keeps its own statement of what happened, and
 * `ui/Notice.tsx` stays the one role="status" notice with no severity variants, a separate thing
 * from this region (`tests/api-errors.test.tsx`).
 *
 * **Mounted once, near the root, and never lazily.** A live region announces a change to content
 * that already exists; a region inserted at the moment its first toast arrives is announced by
 * some screen readers and silently by others. So `sonner` is expected in the first response, and
 * `tests/bundle-split.test.ts` does not list it among the libraries a route must split.
 *
 * Task ids: M27.10.2
 */

import { CircleCheckIcon, InfoIcon, Loader2Icon, OctagonXIcon, TriangleAlertIcon } from "lucide-react";
import { useSyncExternalStore, type CSSProperties } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import { getTheme, subscribeToTheme } from "../../theme/theme";

/** What the region is called when a screen reader lands on it. */
export const TOAST_REGION_LABEL = "Messages";

function Toaster(props: ToasterProps) {
  const theme = useSyncExternalStore(subscribeToTheme, getTheme, getTheme);
  return (
    <Sonner
      theme={theme}
      containerAriaLabel={TOAST_REGION_LABEL}
      icons={{
        success: <CircleCheckIcon className="size-4" aria-hidden="true" />,
        info: <InfoIcon className="size-4" aria-hidden="true" />,
        warning: <TriangleAlertIcon className="size-4" aria-hidden="true" />,
        error: <OctagonXIcon className="size-4" aria-hidden="true" />,
        loading: <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />,
      }}
      style={
        {
          "--normal-bg": "var(--panel)",
          "--normal-text": "var(--ink)",
          "--normal-border": "var(--line)",
          "--border-radius": "var(--corner)",
        } as CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "font-sans",
          description: "text-muted-foreground!",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
