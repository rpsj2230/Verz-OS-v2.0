/**
 * The small parts every module page is built from: a headed card, a labelled fact, a chip, a note
 * saying what is true today, and the Advanced section.
 *
 * **Two kinds of control, and they are kept visibly apart**, because the owner's rule for these
 * pages is no fake functionality. A control whose route exists is an ordinary `Button` or link. A
 * control whose route does not exist, and a capability the product does not offer, are an
 * `Explanation` (`kit/explanation.tsx`): one component in three forms, so how an unavailable act is
 * drawn, and the rule that it is never hidden, is written once. Until 2026-10-15 this file drew two
 * of them (`UnavailableAction` and `NotOffered`) and a third was the `soon` and `not-yet` kinds of
 * `Note`; none of the three is here any more.
 *
 * **Internal identifiers live in `Advanced` and nowhere else on a page.** A slug, a principal id or
 * a template id is how the system names a thing, not how a person does, and the owner found the
 * agent pages cluttered with them. An administrator who needs one to quote in a support request
 * opens the section; everybody else reads names.
 *
 * Every root element carries `data-slot`, which is what `theme/preflight.css` scopes the reset to,
 * so these parts render the same on a page that still has old stylesheets around it.
 *
 * Task ids: M27.10.2, M27.16.2
 */

import { CircleCheck, Info } from "lucide-react";
import { useEffect, useId, type ReactNode } from "react";
import { toast } from "sonner";
import { cn } from "../../lib/utils";

/** The Advanced section's own summary line. */
export const ADVANCED_LABEL = "Advanced";

/** Said once inside the Advanced section, so nobody mistakes an identifier for a name. */
export const ADVANCED_LEDE = "Identifiers the system uses, for quoting in a support request.";

type HeadingLevel = "h2" | "h3";

/**
 * A headed card: a title, a sentence under it, an action at its right, and a footer for notes.
 *
 * **`hideTitle` is for a card whose title is the page's own.** A list drawn directly under a heading
 * of the same name needs the name for a screen reader, which finds the card by its label, and does not
 * need to read it twice with the eye: two headings saying the same thing look like two panels.
 * `tests/console-cleanup.test.tsx` refuses a page that draws one heading twice. The heading stays in
 * the document, visually hidden, so the card is still a labelled region; and the header row is not
 * drawn at all when there is no sentence or action to put in it.
 */
export function SectionCard({
  title,
  lede,
  action,
  children,
  footer,
  className,
  headingLevel = "h2",
  hideTitle = false,
  id,
}: {
  readonly title: string;
  readonly lede?: ReactNode | undefined;
  readonly action?: ReactNode | undefined;
  readonly children: ReactNode;
  readonly footer?: ReactNode | undefined;
  readonly className?: string | undefined;
  readonly headingLevel?: HeadingLevel | undefined;
  /** The title is the page's own: keep it for a screen reader and do not draw it. */
  readonly hideTitle?: boolean | undefined;
  readonly id?: string | undefined;
}) {
  const headingId = useId();
  const Heading = headingLevel;
  const bareHeader = hideTitle && lede === undefined && action === undefined;
  return (
    <section
      data-slot="section-card"
      aria-labelledby={headingId}
      id={id}
      className={cn("flex min-w-0 flex-col rounded-md border border-line bg-panel", className)}
    >
      <div className={cn("flex items-start justify-between gap-3 border-b border-line px-4 py-3", bareHeader && "sr-only")}>
        <div className="min-w-0">
          <Heading id={headingId} className={cn("m-0 text-sm font-semibold text-ink", hideTitle && "sr-only")}>
            {title}
          </Heading>
          {lede === undefined ? null : <p className="m-0 mt-0.5 text-[12.5px] leading-snug text-dim">{lede}</p>}
        </div>
        {action === undefined ? null : <div className="flex shrink-0 flex-wrap items-center gap-1.5">{action}</div>}
      </div>
      <div className="min-w-0 px-4 py-3">{children}</div>
      {footer === undefined ? null : <div className="flex flex-col gap-1.5 border-t border-line bg-sunk px-4 py-2.5">{footer}</div>}
    </section>
  );
}

/** A list of labelled facts. The label column collapses above the value on a phone. */
export function FactList({ children, className }: { readonly children: ReactNode; readonly className?: string | undefined }) {
  return (
    <dl data-slot="fact-list" className={cn("m-0 flex min-w-0 flex-col", className)}>
      {children}
    </dl>
  );
}

/** One labelled fact. The value may wrap anywhere, because an identifier from the API may not. */
export function Fact({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div
      data-slot="fact"
      className="[display:grid] grid-cols-1 gap-1 border-b border-line py-2.5 text-[13px] first:pt-0 last:border-b-0 last:pb-0 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3"
    >
      <dt className="text-dim">{label}</dt>
      <dd className="m-0 min-w-0 text-ink [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

/** A rounded label for a connector, a skill or a channel. Text only; never a control. */
export function Chip({
  children,
  icon,
  tone = "plain",
  mono = false,
  title,
}: {
  readonly children: ReactNode;
  readonly icon?: ReactNode | undefined;
  readonly tone?: "plain" | "requested" | "brand" | undefined;
  readonly mono?: boolean | undefined;
  readonly title?: string | undefined;
}) {
  return (
    <span
      data-slot="chip"
      title={title}
      className={cn(
        "inline-flex min-h-7 max-w-full items-center gap-1.5 rounded-full border px-2.5 text-[12.5px] [overflow-wrap:anywhere]",
        mono && "font-mono text-[11.5px]",
        tone === "plain" && "border-line bg-panel text-ink",
        tone === "requested" && "border-dashed border-line bg-transparent text-dim",
        tone === "brand" && "border-transparent bg-acc-wash text-acc-text",
        "[&>svg]:size-3.5 [&>svg]:shrink-0",
      )}
    >
      {icon}
      <span className="min-w-0">{children}</span>
    </span>
  );
}

/**
 * What each kind of note leads with. `attention` is a line the page composed about what just
 * happened or what is wrong now (a level that cannot answer, a run that removed nothing, a test that
 * failed): it says nothing about an act that is unavailable, which is an `Explanation`, and it
 * leads with nothing. The owner asked for these words and no package codes. The two
 * leads for what is not built or not on, "Coming soon: " and "Not available yet: ", belong to an
 * `Explanation`, which is the one component that says so.
 *
 * `works` says what a feature does today; `done` says that an act a person just took was done,
 * and leads with nothing. Until 2026-09-29 the confirmation after an act was a `works` note, so the
 * owner's install read "Works today: ... is now switched off" and "Works today:" over a Models test
 * that had failed.
 */
export const NOTE_LEADS = Object.freeze({
  works: "Works today: ",
  done: "",
  info: "",
  attention: "",
});

export type NoteKind = keyof typeof NOTE_LEADS;

/**
 * A line saying what is true today, in plain words for an administrator. Never a control, and
 * never a package code, a route or an internal name: those are for whoever builds the thing.
 *
 * **A `done` note is also announced as a toast (M27.10.2), and the note stays.** It is the page's
 * statement that a write took effect, so it is the one place every page already says so, and
 * announcing from here gives all of them the toast region without an edit to each page. The sentence
 * is the note's own, so the toast can say nothing the page does not, and only a sentence is
 * announced: a note holding markup is not turned into text by guessing. The toast carries the
 * sentence as its id, so a note that is drawn again does not announce again while the first shows.
 * The page keeps its note because a toast disappears and a screen reader may be mid-sentence when it
 * arrives (`components/ui/sonner.tsx`).
 */
export function Note({ children, kind = "info" }: { readonly children: ReactNode; readonly kind?: NoteKind | undefined }) {
  const sentence = kind === "done" && typeof children === "string" && children !== "" ? children : null;
  useEffect(() => {
    if (sentence !== null) {
      toast.success(sentence, { id: sentence });
    }
  }, [sentence]);
  const Icon = kind === "works" || kind === "done" ? CircleCheck : Info;
  const lead = NOTE_LEADS[kind];
  return (
    <p
      data-slot="note"
      data-kind={kind}
      className={cn(
        "m-0 flex items-start gap-1.5 text-[12px] leading-relaxed",
        kind === "works" || kind === "done" ? "text-ok" : kind === "attention" ? "text-warn" : "text-dim",
      )}
    >
      <Icon aria-hidden className="mt-[3px] size-3.5 shrink-0" />
      <span className="min-w-0">
        {lead === "" ? null : <span className="font-semibold">{lead}</span>}
        {children}
      </span>
    </p>
  );
}

/**
 * The one place a page may show an internal identifier. Closed until somebody opens it, and a
 * native disclosure, so it opens from the keyboard with no handler.
 */
export function Advanced({ children }: { readonly children: ReactNode }) {
  return (
    <details data-slot="advanced" className="group rounded-md border border-line bg-panel">
      <summary className="flex min-h-11 cursor-pointer items-center px-4 text-[13px] font-medium text-ink sm:min-h-9">
        {ADVANCED_LABEL}
      </summary>
      <div className="flex flex-col gap-2 border-t border-line px-4 py-3">
        <p className="m-0 text-[12px] text-dim">{ADVANCED_LEDE}</p>
        {children}
      </div>
    </details>
  );
}

/**
 * The letters a name is drawn as where a picture would go: the first letters of its first and last
 * words, or one letter for one word.
 *
 * Computed from the name already on the screen rather than fetched, because no entity here has an
 * image field and a picture would be a second fact and a request to somewhere this console does not
 * control. Upper cased in a fixed locale, so the letters do not depend on the browser's: under a
 * Turkish locale a lower case i becomes a different letter, and an avatar that differs by the reader's
 * machine is a difference two people comparing screens can see.
 */
export function initialsOf(name: string): string {
  const words = name.split(/\s+/u).filter((word) => word.length > 0);
  const first = words[0] ?? "";
  const last = words.length > 1 ? (words[words.length - 1] ?? "") : "";
  return `${first.slice(0, 1)}${last.slice(0, 1)}`.toLocaleUpperCase("en-GB");
}
