/**
 * Choosing a person by name: a search over the directory this reader may see, and the people it
 * answered, one of whom is chosen.
 *
 * **Names, never typed identifiers.** An appointment or a placement names a principal, and the old
 * forms asked for the principal id to be typed, which nobody knows. This asks the directory route
 * (`GET /govern/directory?q=`), which answers only people the reader may be shown, and the chosen
 * person's id travels in the request without being drawn.
 *
 * **Nothing here decides who may be chosen.** The route that writes asks its own question about the
 * person as the database holds them; a person offered here may still be refused there, in the API's
 * words.
 *
 * Task ids: M27.11.3, M27.16.1
 */

import { useId, useMemo, useState } from "react";
import { useResource } from "../../api/useResource";
import { listPath, NO_QUESTION } from "../../components/listing";
import { Input } from "../../components/ui/input";
import { cn } from "../../lib/utils";
import { DIRECTORY_API_PATH, readPeople, type PersonRow } from "../people/peopleQuery";

/** How many people one search offers. */
const OFFERED = 8;

export function PersonPicker({
  label,
  hint,
  chosen,
  onChoose,
  problem,
  exclude = [],
}: {
  readonly label: string;
  readonly hint?: string | undefined;
  readonly chosen: PersonRow | null;
  readonly onChoose: (person: PersonRow | null) => void;
  readonly problem?: string | null | undefined;
  /** People not to offer, such as those already in the team. */
  readonly exclude?: readonly string[] | undefined;
}) {
  const id = useId();
  const [typed, setTyped] = useState("");
  const words = typed.trim();
  const answer = useResource<unknown>(words.length < 2 ? null : listPath(DIRECTORY_API_PATH, { ...NO_QUESTION, search: words }, null, OFFERED));
  const offered = useMemo(
    () => (words.length < 2 ? [] : readPeople(answer.data).filter((one) => !exclude.includes(one.principalId))),
    [answer.data, words, exclude],
  );
  const hintId = `${id}-hint`;
  const problemId = `${id}-problem`;
  return (
    <div data-slot="person-picker" className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      <p id={hintId} className="m-0 text-[12px] leading-snug text-dim">
        {hint ?? "Type at least two letters of their name, then choose them from the list."}
      </p>
      {chosen === null ? (
        <>
          <Input
            id={id}
            type="search"
            autoComplete="off"
            aria-describedby={[hintId, problem ? problemId : ""].filter((one) => one !== "").join(" ")}
            aria-invalid={problem ? true : undefined}
            className="h-11 sm:h-9"
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
          {offered.length === 0 ? null : (
            <ul aria-label={`People matching ${words}`} className="m-0 flex list-none flex-col rounded-md border border-line p-0">
              {offered.map((one) => (
                <li key={one.principalId} className="border-b border-line last:border-b-0">
                  <button
                    type="button"
                    className={cn("flex min-h-11 w-full flex-col items-start px-3 py-1.5 text-left text-[13px] hover:bg-sunk sm:min-h-9")}
                    onClick={() => {
                      onChoose(one);
                      setTyped("");
                    }}
                  >
                    <span className="font-medium text-ink">{one.displayName}</span>
                    {one.departmentName ?? one.department ? <span className="text-[12px] text-dim">{one.departmentName ?? one.department}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {words.length >= 2 && answer.data !== null && offered.length === 0 ? (
            <p className="m-0 text-[12px] text-dim">Nobody you may see matches.</p>
          ) : null}
        </>
      ) : (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-sunk px-3 py-2 text-[13px]">
          <span className="font-medium text-ink">{chosen.displayName}</span>
          <button
            type="button"
            className="ml-auto text-[12.5px] text-acc-text underline-offset-4 hover:underline"
            onClick={() => {
              onChoose(null);
            }}
          >
            Choose somebody else
          </button>
        </div>
      )}
      {problem ? (
        <p id={problemId} className="m-0 text-[12px] text-crit">
          {problem}
        </p>
      ) : null}
    </div>
  );
}
