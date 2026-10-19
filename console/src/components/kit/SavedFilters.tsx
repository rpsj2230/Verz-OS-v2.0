/**
 * "Saved filters" on a list's toolbar: keep the search and filters just asked under a name, and ask
 * them again with one press.
 *
 * **Drawn only for a known person.** The entries live in this browser under the principal the shell
 * learnt from `GET /me` (`kit/caller.tsx`), so a shared computer shows nobody else's questions, and
 * a page mounted without a known caller draws no control rather than one that would keep things under
 * nobody. The storage and its rules are `kit/savedFilterStore.ts`; this is only the control.
 *
 * **It lists names the person wrote and nothing else.** Not the values a filter holds, and never a
 * number: a saved filter whose value has since become invisible to the reader would otherwise be
 * drawn naming that value, and a count of "saved" or "matching" would be a total over rows. Applying
 * one asks the route again, which answers over what this reader may see
 * (`A_SAVED_FILTER_ASKS_AGAIN_AND_NEVER_ANSWERS`).
 *
 * **Forgetting is not an act on the company's data.** It removes the person's own bookmark from their
 * own browser, so it is not confirmed through a dialog: it is undone by saving the same search again.
 *
 * Task ids: M27.16.3
 */

import { Bookmark, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { useInRouterContext, useLocation } from "react-router-dom";
import type { ListQuestion } from "../listing";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { useCallerId } from "./caller";
import {
  MAX_NAME,
  MAX_SAVED,
  fitToList,
  forgetFilter,
  holdsAQuestion,
  readSavedFilters,
  saveFilter,
  type SavedFilter,
} from "./savedFilterStore";

export const SAVED_FILTERS_LABEL = "Saved filters";
export const NOTHING_SAVED = "Nothing saved yet. Search or filter the list, then save it here.";
export const NAME_LABEL = "Name for this search";
export const SAVE_LABEL = "Save this search";
export const KEPT_IN_THIS_BROWSER =
  "Kept in this browser for you only. It does not follow you to another computer.";
export const SAVED_SENTENCE = "Saved.";
export const FORGOTTEN_SENTENCE = "Forgotten.";
export const COULD_NOT_KEEP = "This browser would not keep it, so it was not saved.";
export const NOTHING_TO_SAVE = "Search or filter the list first, then save it.";
export const NEEDS_A_NAME = "Give it a name first.";
export const FULL_SENTENCE = "You keep as many as this list holds. Forget one to save another.";

/** What each refusal to save says, in words. */
const WHY: Readonly<Record<"no-name" | "nothing-to-save" | "full" | "unavailable", string>> = {
  "no-name": NEEDS_A_NAME,
  "nothing-to-save": NOTHING_TO_SAVE,
  full: FULL_SENTENCE,
  unavailable: COULD_NOT_KEEP,
};

export function SavedFilters(props: {
  readonly label: string;
  readonly question: ListQuestion;
  readonly columns: readonly string[];
  readonly sorts: readonly string[];
  readonly onApply: (question: ListQuestion) => void;
}) {
  const person = useCallerId();
  const routed = useInRouterContext();
  if (person === null || !routed) {
    return null;
  }
  return <Kept person={person} {...props} />;
}

function Kept({
  person,
  label,
  question,
  columns,
  sorts,
  onApply,
}: {
  readonly person: string;
  readonly label: string;
  readonly question: ListQuestion;
  readonly columns: readonly string[];
  readonly sorts: readonly string[];
  readonly onApply: (question: ListQuestion) => void;
}) {
  const { pathname } = useLocation();
  const list = `${pathname}|${label}`;
  const [kept, setKept] = useState<readonly SavedFilter[]>(() => readSavedFilters(person, list));
  const [name, setName] = useState("");
  const [said, setSaid] = useState("");
  const [open, setOpen] = useState(false);
  const nameId = useId();
  const canSave = holdsAQuestion(question);
  const fullForThisName = kept.length >= MAX_SAVED && !kept.some((one) => one.name === name.trim());

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          // Read again on opening, so a second tab's changes are what is shown.
          setKept(readSavedFilters(person, list));
          setSaid("");
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="min-h-11 sm:min-h-8">
          <Bookmark aria-hidden /> {SAVED_FILTERS_LABEL}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 gap-3">
        <div className="flex flex-col gap-1">
          <p className="m-0 text-sm font-medium text-ink">{SAVED_FILTERS_LABEL}</p>
          <p className="m-0 text-[12.5px] text-dim">{KEPT_IN_THIS_BROWSER}</p>
        </div>
        {kept.length === 0 ? (
          <p className="m-0 text-[12.5px] text-body">{NOTHING_SAVED}</p>
        ) : (
          <ul aria-label={SAVED_FILTERS_LABEL} className="m-0 flex list-none flex-col gap-1 p-0">
            {kept.map((one) => (
              <li key={one.name} className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="quiet"
                  size="sm"
                  className="min-h-11 min-w-0 flex-1 justify-start sm:min-h-8"
                  onClick={() => {
                    onApply(fitToList(one, columns, sorts));
                    setOpen(false);
                  }}
                >
                  <span className="truncate">{one.name}</span>
                </Button>
                <Button
                  type="button"
                  variant="quiet"
                  size="icon-sm"
                  className="size-11 sm:size-8"
                  aria-label={`Forget ${one.name}`}
                  onClick={() => {
                    setKept(forgetFilter(person, list, one.name));
                    setSaid(FORGOTTEN_SENTENCE);
                  }}
                >
                  <Trash2 aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {canSave ? (
          <form
            className="flex flex-col gap-2"
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              const outcome = saveFilter(person, list, name, question);
              setKept(outcome.filters);
              if (outcome.saved) {
                setName("");
                setSaid(SAVED_SENTENCE);
              } else {
                setSaid(WHY[outcome.why]);
              }
            }}
          >
            <label htmlFor={nameId} className="text-[12.5px] text-dim">
              {NAME_LABEL}
            </label>
            <Input
              id={nameId}
              value={name}
              maxLength={MAX_NAME}
              className="h-11 sm:h-8"
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
            <Button type="submit" size="sm" className="min-h-11 self-start sm:min-h-8" disabled={fullForThisName}>
              {SAVE_LABEL}
            </Button>
            {fullForThisName ? <p className="m-0 text-[12.5px] text-dim">{FULL_SENTENCE}</p> : null}
          </form>
        ) : null}
        <p role="status" className="m-0 min-h-4 text-[12.5px] text-dim">
          {said}
        </p>
      </PopoverContent>
    </Popover>
  );
}
