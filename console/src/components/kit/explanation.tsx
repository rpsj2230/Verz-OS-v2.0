/**
 * The explanation: "this cannot be done yet" and "why you cannot do this here", in one component.
 *
 * `docs/admin-console-architecture.md` 5.2 asks every act the install cannot yet perform, and every
 * act a reader cannot perform where they are, to be explained in a sentence and never hidden. Until
 * 2026-10-15 that was three components that each drew the markup for themselves: `UnavailableAction`
 * (an inert control with its reason), `NotOffered` (a sentence in place of a control) and `Note` with
 * its `soon` and `not-yet` kinds (a line). A change to how an explanation looks, or to the rule that
 * an explanation is never hidden, had to be made in three places and was made in one at a time. They
 * are three **forms** of this one component now, and the three old names are gone.
 *
 * **Three forms, one appearance.** `action` is a control that cannot be pressed: focusable, so a
 * keyboard reaches the reason, inert, so pressing it changes nothing, dashed, so nobody reads it as
 * live, and carrying its reason as its description. `line` is a sentence in place of a control, for
 * something this product does not offer at all, because a disabled switch still says "this could be
 * switched on". `note` is a line saying what is true today, with the lead "Coming soon: " or "Not
 * available yet: " when the sentence is about something not built or not on.
 *
 * **The sentence is served, never written here or on the page.** A page names the act
 * (`act="agent.level"`) and this component asks `GET /console/explanations/{act}` for the words, so a
 * sentence the server holds is drawn exactly as served, and goes when the route it waits for lands
 * (`brain.console.explanations`). A sentence the API already sends with the row it is about (a vault
 * that is not ready, a publish that is held) is handed in as `told`. `tests/explanations.test.ts`
 * holds every use in the console to one or the other: a literal, a typed constant or a sentence
 * joined from pieces on a page is refused. The one sentence typed here is `EXPLANATION_NOT_READ`, for
 * the case where the answer itself could not be read: an explanation is never hidden, and the failure
 * to read one cannot be explained by another.
 *
 * **While the words are on their way a control is drawn already**, inert, so nothing moves when they
 * arrive; a line or a note is drawn when they do. `aria-disabled` rather than `disabled` on the
 * control, on purpose: a disabled button leaves the tab order, and then a keyboard user never meets
 * the sentence that says why.
 *
 * Task ids: M27.15.70, M27.10.2
 */

import { Ban, CircleDashed } from "lucide-react";
import { useId, type ReactNode } from "react";
import { useResource } from "../../api/useResource";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { EXPLANATION_NOT_READ, explanationApiPath, readExplanation, type ExplanationLead } from "./explanationQuery";

/** What an unavailable control is marked with, so a test can find every one on a page. */
export const UNAVAILABLE_MARK = "data-unavailable";

/** What a note about something not built or not on leads with. */
export const EXPLANATION_LEADS = Object.freeze({
  soon: "Coming soon: ",
  "not-yet": "Not available yet: ",
});

/** Where the words come from: the registered act, or a sentence the API sent with the row. */
type Words = { readonly act: string } | { readonly told: string };

type ActionForm = {
  readonly form: "action";
  /** What the control would do, as its accessible name when it shows no text. */
  readonly label: string;
  readonly icon?: ReactNode | undefined;
  /** The visible words, when the control is not an icon. */
  readonly text?: string | undefined;
  readonly size?: "sm" | "xs" | "icon-sm" | undefined;
  readonly className?: string | undefined;
};

type LineForm = {
  readonly form: "line";
};

type NoteForm = {
  readonly form: "note";
  /** Said first. A registered act carries its own; a sentence the API sent says which it is here. */
  readonly lead?: Exclude<ExplanationLead, ""> | undefined;
};

export type ExplanationProps = Words & (ActionForm | LineForm | NoteForm);

/** What the words are, once asked for: nothing yet, the sentence, or that it could not be read. */
interface Heard {
  readonly sentence: string | null;
  readonly lead: ExplanationLead;
}

/** Ask for the act's words, or take the ones the API sent. Never both, and never neither. */
function useWords(words: Words, own: ExplanationLead | undefined): Heard {
  const act = "act" in words ? words.act : null;
  const answer = useResource<unknown>(act === null ? null : explanationApiPath(act));
  if ("told" in words) {
    return { sentence: words.told, lead: own ?? "not-yet" };
  }
  if (answer.busy) {
    return { sentence: null, lead: own ?? "" };
  }
  const served = answer.data === null ? null : readExplanation(answer.data);
  if (served === null) {
    return { sentence: EXPLANATION_NOT_READ, lead: "" };
  }
  return { sentence: served.sentence, lead: own ?? served.lead };
}

/** The mark a test finds an explanation by: the act, or that the API told it. */
function markOf(words: Words): string {
  return "act" in words ? words.act : "told";
}

function Action({ words, label, icon, text, size = "sm", className }: Omit<ActionForm, "form"> & { readonly words: Words }) {
  const describedBy = useId();
  const { sentence } = useWords(words, undefined);
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
            data-explains={markOf(words)}
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
        {sentence === null ? null : (
          <TooltipContent side="top" className="max-w-[18rem] text-[12px] leading-snug">
            {sentence}
          </TooltipContent>
        )}
      </Tooltip>
      <span id={describedBy} className="sr-only">
        {sentence}
      </span>
    </TooltipProvider>
  );
}

function Line({ words }: { readonly words: Words }) {
  const { sentence } = useWords(words, undefined);
  if (sentence === null) {
    return null;
  }
  return (
    <p
      data-slot="not-offered"
      data-explains={markOf(words)}
      className="m-0 flex items-start gap-1.5 text-[12.5px] leading-snug text-dim"
    >
      <Ban aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <span>{sentence}</span>
    </p>
  );
}

function NoteLine({ words, lead }: Omit<NoteForm, "form"> & { readonly words: Words }) {
  const heard = useWords(words, lead);
  if (heard.sentence === null) {
    return null;
  }
  return (
    <p
      data-slot="note"
      data-kind={heard.lead === "" ? "info" : heard.lead}
      data-explains={markOf(words)}
      className="m-0 flex items-start gap-1.5 text-[12px] leading-relaxed text-warn"
    >
      <CircleDashed aria-hidden className="mt-[3px] size-3.5 shrink-0" />
      <span className="min-w-0">
        {heard.lead === "" ? null : <span className="font-semibold">{EXPLANATION_LEADS[heard.lead]}</span>}
        {heard.sentence}
      </span>
    </p>
  );
}

/** One explanation, in the form the place it is drawn needs. */
export function Explanation(props: ExplanationProps) {
  const words: Words = "act" in props ? { act: props.act } : { told: props.told };
  switch (props.form) {
    case "action":
      return <Action words={words} label={props.label} icon={props.icon} text={props.text} size={props.size} className={props.className} />;
    case "line":
      return <Line words={words} />;
    case "note":
      return <NoteLine words={words} lead={props.lead} />;
  }
}
