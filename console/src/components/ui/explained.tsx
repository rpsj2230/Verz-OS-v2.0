/**
 * The explanation panel: "this cannot be done here yet" and "why you cannot do this here", in one
 * appearance, with a way on when there is one.
 *
 * Written here rather than copied: shadcn/ui's alert has a destructive variant, and this has none.
 *
 * **One appearance, and that is the rule this component exists to hold.** An explanation that turned
 * red for one reason and grey for another would make its colour say which reason applied, and the
 * reason is the part that discloses, which is the argument `ui/Lock.tsx` makes by taking no props and
 * `ui/Notice.tsx` makes by having no severity. So there is no tone, no variant and no icon that
 * varies, and `tests/ui-structure.test.tsx` holds the exact list of what it can be told.
 *
 * **What it may say is bounded by rule R1 of the console plan.** Telling a person what their own
 * sign-in cannot do is allowed, and so is announcing a halt or a switched-off feature with a link to
 * where it is switched on (R11). Saying that something exists which the reader may not see is not,
 * and the sentence therefore comes from the served constants a page already renders, not from
 * text composed here. `role="note"`, because it is supplementary to the page rather than a status
 * that changed.
 *
 * Task ids: M27.10.2
 */

import { useId, type ReactNode } from "react";
import { cn } from "../../lib/utils";

type HeadingLevel = "h2" | "h3" | "h4";

function Explained({
  title,
  children,
  action,
  headingLevel = "h2",
  className,
}: {
  /** What cannot be done, as the page's own heading. */
  title: string;
  /** Why, in the served sentence. */
  children: ReactNode;
  /** The one way on, when there is one: a link to where it is switched on, or to sign in again. */
  action?: ReactNode;
  headingLevel?: HeadingLevel;
  className?: string;
}) {
  const headingId = useId();
  const Heading = headingLevel;
  return (
    <section
      data-slot="explained"
      role="note"
      aria-labelledby={headingId}
      className={cn("flex flex-col gap-2 rounded-lg border border-border bg-muted px-4 py-3 text-sm text-body", className)}
    >
      <Heading id={headingId} className="m-0 font-heading text-sm leading-snug font-medium text-foreground">
        {title}
      </Heading>
      <div data-slot="explained-body" className="[&>p]:m-0">
        {children}
      </div>
      {action === undefined ? null : (
        <div data-slot="explained-action" className="flex flex-wrap gap-2">
          {action}
        </div>
      )}
    </section>
  );
}

export { Explained };
