/**
 * Which kinds of memory an agent may read and write, on its Memory section, and the confirmed
 * change (M39.7.1).
 *
 * **The boxes are the route's, never a list written here.** `GET /agents/{id}/memory-kinds` sends
 * the five kinds, each with its words and whether it is on, to anybody the agent's audience covers,
 * and says whether this reader may change them. A kind left out is not read by any run of the agent
 * and is deleted from nowhere: the note under the boxes is the route's own sentence saying so.
 *
 * **The change goes through `kit/ConfirmDialog`**, because unticking a kind stops every run of the
 * agent being shown it, for everybody, which `tests/destructive-confirmed.test.ts` counts as switching
 * something off. The body sends the kinds the card drew as `expected`, so a page that went stale is
 * the route's 409 in its own sentence and nothing is written. Only a reader the route says may change
 * them is offered the button, and the route asks again whatever the page believed.
 *
 * Task ids: M39.7.1
 */

import { useId, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";

export const MEMORY_KINDS_HEADING = "What it may remember";
export const MEMORY_KINDS_LEDE = "The kinds of memory this agent reads and writes. Leaving one out stops it being shown, and deletes nothing.";
export const CHANGE_MEMORY_KINDS = "Change what it may remember";
export const MEMORY_KINDS_QUESTION = (name: string): string => `Change what ${name} may remember?`;
export const MEMORY_KINDS_CONSEQUENCE =
  "It reads and writes the kinds ticked and no others. A kind unticked is no longer shown to it for anybody, from the next question on. Nothing is deleted, and ticking it again shows it again.";
export const MEMORY_KINDS_DONE = "What it may remember was changed";
export const MEMORY_KINDS_NOT_CHANGED = "Nothing was changed";
export const NO_KIND_ON = "No kind of memory is switched on, so this agent remembers nothing.";

export interface KindChoice {
  readonly name: string;
  readonly label: string;
  readonly hint: string;
  readonly on: boolean;
}

export interface MemoryKindsShown {
  readonly agentId: string;
  readonly kinds: readonly KindChoice[];
  readonly mayChange: boolean;
  readonly note: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field is read back
  // through a type test below.
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

export function agentMemoryKindsApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/memory-kinds`;
}

/** The kinds read out of a body, or null when the body is not one. */
export function readMemoryKinds(payload: unknown): MemoryKindsShown | null {
  const fields = fieldsOf(payload);
  if (fields === null || typeof fields["agent_id"] !== "string" || !Array.isArray(fields["kinds"])) {
    return null;
  }
  const kinds = (fields["kinds"] as readonly unknown[])
    .map(fieldsOf)
    .filter((one): one is Fields => one !== null && typeof one["name"] === "string")
    .map((one) => ({
      name: String(one["name"]),
      label: typeof one["label"] === "string" ? one["label"] : String(one["name"]),
      hint: typeof one["hint"] === "string" ? one["hint"] : "",
      on: one["on"] === true,
    }));
  return {
    agentId: fields["agent_id"],
    kinds,
    mayChange: fields["may_change"] === true,
    note: typeof fields["note"] === "string" ? fields["note"] : "",
  };
}

/** The body a change sends: the kinds ticked and the kinds the card drew. */
export function memoryKindsBody(shown: MemoryKindsShown, chosen: ReadonlySet<string>): { kinds: string[]; expected: string[] } {
  return {
    kinds: shown.kinds.filter((one) => chosen.has(one.name)).map((one) => one.name),
    expected: shown.kinds.filter((one) => one.on).map((one) => one.name),
  };
}

interface Refused {
  readonly failure: ApiFailure;
  readonly sentence?: string;
}

function sentenceOf(body: unknown): string | undefined {
  const fields = fieldsOf(body);
  return fields !== null && typeof fields["sentence"] === "string" ? fields["sentence"] : undefined;
}

export function AgentMemoryKinds({ agentId }: { readonly agentId: string }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentMemoryKindsApiPath(agentId), version);
  const shown = useMemo(() => (answer.data === null ? null : readMemoryKinds(answer.data)), [answer.data]);
  const [editing, setEditing] = useState<MemoryKindsShown | null>(null);
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const [refused, setRefused] = useState<Refused | null>(null);
  const legend = useId();

  if (shown === null) {
    return null;
  }

  const confirm = () => {
    if (editing === null) {
      return;
    }
    const drawn = editing;
    setSending(true);
    void (async () => {
      const result = await request<unknown>(agentMemoryKindsApiPath(drawn.agentId), {
        method: "POST",
        body: memoryKindsBody(drawn, chosen),
      });
      setSending(false);
      setEditing(null);
      if (result.ok) {
        setDone(true);
        setVersion((count) => count + 1);
        return;
      }
      const sentence = result.failure.status === 409 ? sentenceOf(result.body) : undefined;
      setRefused(sentence === undefined ? { failure: result.failure } : { failure: result.failure, sentence });
    })();
  };

  const on = shown.kinds.filter((one) => one.on);
  return (
    <SectionCard
      title={MEMORY_KINDS_HEADING}
      lede={MEMORY_KINDS_LEDE}
      action={
        shown.mayChange ? (
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 sm:min-h-8"
            disabled={sending}
            onClick={() => {
              setDone(false);
              setRefused(null);
              setChosen(new Set(on.map((one) => one.name)));
              setEditing(shown);
            }}
          >
            {CHANGE_MEMORY_KINDS}
          </Button>
        ) : undefined
      }
    >
      <div data-slot="agent-memory-kinds" className="flex min-w-0 flex-col gap-2">
        {refused === null ? null : (
          <FailureNotice
            failure={refused.failure}
            title={MEMORY_KINDS_NOT_CHANGED}
            {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
          />
        )}
        {done ? <Notice title={MEMORY_KINDS_DONE}>{agentId}</Notice> : null}
        {on.length === 0 ? (
          <Note>{NO_KIND_ON}</Note>
        ) : (
          <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
            {shown.kinds.map((one) => (
              <li key={one.name} data-kind={one.name} data-on={one.on ? "yes" : "no"} className={one.on ? "text-ink" : "text-dim line-through"}>
                {one.label}
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog
        open={editing !== null}
        question={editing === null ? "" : MEMORY_KINDS_QUESTION(agentId)}
        consequence={MEMORY_KINDS_CONSEQUENCE}
        details={
          editing === null ? undefined : (
            <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0" aria-labelledby={legend}>
              <legend id={legend} className="text-sm font-medium text-ink">
                {MEMORY_KINDS_HEADING}
              </legend>
              {editing.kinds.map((one) => (
                <label key={one.name} className="flex min-h-11 items-start gap-2 text-sm sm:min-h-8">
                  <input
                    type="checkbox"
                    name="memory-kinds"
                    value={one.name}
                    className="mt-1"
                    checked={chosen.has(one.name)}
                    onChange={(event) => {
                      const next = new Set(chosen);
                      if (event.target.checked) {
                        next.add(one.name);
                      } else {
                        next.delete(one.name);
                      }
                      setChosen(next);
                    }}
                  />
                  <span className="flex flex-col">
                    {one.label}
                    <span className="text-[12px] text-dim">{one.hint}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          )
        }
        confirmLabel="Save"
        cancelLabel="Not now"
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setEditing(null);
        }}
      />
    </SectionCard>
  );
}
