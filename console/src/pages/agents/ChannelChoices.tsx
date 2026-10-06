/**
 * The channels a new agent answers on, one box each, none ticked (M13.7.4).
 *
 * The boxes are the server's list (`ChannelChoiceView`), never a list written here, so a channel the
 * product adds is offered the day it is declared and one it cannot answer on is never offered. The
 * sentence under the legend is the server's too: an agent with none ticked answers nowhere, and the
 * person making it is told so before they press, not after nobody can reach it.
 *
 * Task ids: M13.7.4
 */

import { useId } from "react";

import type { ChannelChoice } from "./agentDraftsQuery";

/** The legend over the boxes. */
export const WHERE_IT_ANSWERS = "Where it answers";

/** The ticked names, in the order the choices are offered. */
export function ticked(choices: readonly ChannelChoice[], chosen: ReadonlySet<string>): string[] {
  return choices.filter((one) => chosen.has(one.name)).map((one) => one.name);
}

export function ChannelChoices({
  choices,
  note,
  chosen,
  onChange,
}: {
  readonly choices: readonly ChannelChoice[];
  readonly note: string;
  readonly chosen: ReadonlySet<string>;
  readonly onChange: (next: ReadonlySet<string>) => void;
}) {
  const noteId = useId();
  if (choices.length === 0) {
    return null;
  }
  return (
    <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0" aria-describedby={noteId}>
      <legend className="text-sm font-medium text-ink">{WHERE_IT_ANSWERS}</legend>
      <p id={noteId} className="m-0 text-[12px] text-dim">
        {note}
      </p>
      {choices.map((one) => (
        <label key={one.name} className="flex min-h-11 items-center gap-2 text-sm sm:min-h-8">
          <input
            type="checkbox"
            name="channels"
            value={one.name}
            className="size-4"
            checked={chosen.has(one.name)}
            onChange={(event) => {
              const next = new Set(chosen);
              if (event.target.checked) {
                next.add(one.name);
              } else {
                next.delete(one.name);
              }
              onChange(next);
            }}
          />
          {one.label}
        </label>
      ))}
    </fieldset>
  );
}
