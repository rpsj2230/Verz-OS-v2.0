/**
 * The small parts every module page is built from: a headed card, a labelled fact, a chip, a note
 * saying what is true today, an action that is not built yet, and the Advanced section.
 *
 * **Two kinds of control, and they are kept visibly apart**, because the owner's rule for these
 * pages is no fake functionality. A control whose route exists is an ordinary `Button` or link. A
 * control whose route does not exist is `UnavailableAction`: focusable, so a keyboard reaches the
 * reason; inert, so pressing it changes nothing; dashed, so nobody reads it as live; and its reason
 * is one plain sentence read out by a screen reader and shown on hover or focus. It is never drawn
 * as a working control, and it is never hidden, because a hidden control says the product has no
 * such act at all. A capability the product does not offer is `NotOffered`, a sentence and no
 * control, because a disabled switch still says "this could be switched on".
 *
 * **Internal identifiers live in `Advanced` and nowhere else on a page.** A slug, a principal id or
 * a template id is how the system names a thing, not how a person does, and the owner found the
 * agent pages cluttered with them. An administrator who needs one to quote in a support request
 * opens the section; everybody else reads names.
 *
 * Every root element carries `data-slot`, which is what `theme/preflight.css` scopes the reset to,
 * so these parts render the same on a page that still has old stylesheets around it.
 *
 * Task ids: M27.10.2
 */

import { Ban, CircleCheck, CircleDashed, Info } from "lucide-react";
import { useId, type ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";

/** What an unavailable control is marked with, so a test can find every one on a page. */
export const UNAVAILABLE_MARK = "data-unavailable";

/** The Advanced section's own summary line. */
export const ADVANCED_LABEL = "Advanced";

/** Said once inside the Advanced section, so nobody mistakes an identifier for a name. */
export const ADVANCED_LEDE = "Identifiers the system uses, for quoting in a support request.";

type HeadingLevel = "h2" | "h3";

/** A headed card: a title, a sentence under it, an action at its right, and a footer for notes. */
export function SectionCard({
  title,
  lede,
  action,
  children,
  footer,
  className,
  headingLevel = "h2",
  id,
}: {
  readonly title: string;
  readonly lede?: ReactNode | undefined;
  readonly action?: ReactNode | undefined;
  readonly children: ReactNode;
  readonly footer?: ReactNode | undefined;
  readonly className?: string | undefined;
  readonly headingLevel?: HeadingLevel | undefined;
  readonly id?: string | undefined;
}) {
  const headingId = useId();
  const Heading = headingLevel;
  return (
    <section
      data-slot="section-card"
      aria-labelledby={headingId}
      id={id}
      className={cn("flex min-w-0 flex-col rounded-md border border-line bg-panel", className)}
    >
      <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <Heading id={headingId} className="m-0 text-sm font-semibold text-ink">
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

/** What each kind of note leads with. The owner asked for these words and no package codes. */
export const NOTE_LEADS = Object.freeze({
  soon: "Coming soon: ",
  "not-yet": "Not available yet: ",
  works: "Works today: ",
  info: "",
});

export type NoteKind = keyof typeof NOTE_LEADS;

/**
 * A line saying what is true today, in plain words for an administrator. Never a control, and
 * never a package code, a route or an internal name: those are for whoever builds the thing.
 */
export function Note({ children, kind = "info" }: { readonly children: ReactNode; readonly kind?: NoteKind | undefined }) {
  const Icon = kind === "soon" || kind === "not-yet" ? CircleDashed : kind === "works" ? CircleCheck : Info;
  const lead = NOTE_LEADS[kind];
  return (
    <p
      data-slot="note"
      data-kind={kind}
      className={cn(
        "m-0 flex items-start gap-1.5 text-[12px] leading-relaxed",
        kind === "soon" || kind === "not-yet" ? "text-warn" : kind === "works" ? "text-ok" : "text-dim",
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
 * A control whose action is not built yet. Focusable, inert, dashed, and carrying its reason.
 *
 * `aria-disabled` rather than `disabled`, on purpose: a disabled button leaves the tab order, and
 * then a keyboard user never meets the sentence that says why. The press is swallowed, so nothing
 * happens however it arrives.
 */
export function UnavailableAction({
  label,
  reason,
  icon,
  text,
  size = "sm",
  className,
}: {
  /** What the control would do, as its accessible name when it shows no text. */
  readonly label: string;
  /** One plain sentence: why it cannot be pressed today. */
  readonly reason: string;
  readonly icon?: ReactNode | undefined;
  /** The visible words, when the control is not an icon. */
  readonly text?: string | undefined;
  readonly size?: "sm" | "xs" | "icon-sm" | undefined;
  readonly className?: string | undefined;
}) {
  const describedBy = useId();
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size={size}
            aria-disabled="true"
            aria-label={text === undefined ? label : undefined}
            aria-describedby={describedBy}
            data-unavailable=""
            onClick={(event) => {
              event.preventDefault();
            }}
            className={cn(
              "min-h-11 cursor-not-allowed border-dashed bg-transparent text-dim shadow-none hover:bg-transparent hover:text-dim sm:min-h-8",
              size === "icon-sm" && "size-11 sm:size-8",
              className,
            )}
          >
            {icon}
            {text === undefined ? null : <span>{text}</span>}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[18rem] text-[12px] leading-snug">
          {reason}
        </TooltipContent>
      </Tooltip>
      <span id={describedBy} className="sr-only">
        {reason}
      </span>
    </TooltipProvider>
  );
}

/** A sentence in place of a control, for something this product does not offer at all. */
export function NotOffered({ children }: { readonly children: ReactNode }) {
  return (
    <p data-slot="not-offered" className="m-0 flex items-start gap-1.5 text-[12.5px] leading-snug text-dim">
      <Ban aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <span>{children}</span>
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

/** The initials a name is drawn as where a picture would go. There is no picture field. */
export function initialsOf(name: string): string {
  const words = name
    .split(/[\s_-]+/)
    .map((one) => one.trim())
    .filter((one) => one !== "");
  const first = words[0]?.charAt(0) ?? "";
  const second = words.length > 1 ? (words[words.length - 1]?.charAt(0) ?? "") : (words[0]?.charAt(1) ?? "");
  return `${first}${second}`.toUpperCase();
}
