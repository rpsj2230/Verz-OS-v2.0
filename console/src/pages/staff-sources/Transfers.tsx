/**
 * The agents of somebody the staff sync marked as having left, and the one act on each: take it on.
 *
 * Taking one on is confirmed, because it changes who answers for the agent and starts it again.
 * The API decides again under a lock whether this reader may, so a row drawn here is an offer and
 * not a promise, and a refusal is drawn in the confirmation where the person is looking. The list
 * is the API's, narrowed per reader, so an empty one says the same sentence whatever the reason.
 *
 * Task ids: M1.8.9, M26.3.2, M27.16.1
 */

import { useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { Chip, ConfirmDialog, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { transferApiPath, type Transfer } from "../staffSourcesQuery";

export const TRANSFERS_HEADING = "Agents waiting for an owner";
export const TRANSFERS_LEDE = "An agent whose owner left stops until somebody takes it on.";
export const NO_TRANSFERS = "No agent is waiting for an owner you may take on.";
export const TAKE_ON = "Take on";
export const KEEP_WAITING = "Leave it waiting";
export const TAKE_ON_CONSEQUENCE =
  "You become the person who answers for it and it starts running again. What it can reach does " +
  "not change, and the change of owner is recorded in the audit ledger.";
export const NOT_TAKEN = "The agent was not taken on";
export const STOPPED = "Stopped";
export const RUNNING = "Running";

/** What the page says once an agent has been taken on. */
export function takenOn(name: string): string {
  return `${name} now answers to you and is running again.`;
}

export function Transfers({
  waiting,
  onDone,
}: {
  readonly waiting: readonly Transfer[];
  readonly onDone: (told: string) => void;
}) {
  const [chosen, setChosen] = useState<Transfer | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function take(agent: Transfer): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(transferApiPath(agent.agent_id), { method: "POST" });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setChosen(null);
      onDone(takenOn(agent.display_name));
    })();
  }

  return (
    <SectionCard title={TRANSFERS_HEADING} lede={TRANSFERS_LEDE}>
      {waiting.length === 0 ? (
        <p className="m-0 text-[13px] text-dim">{NO_TRANSFERS}</p>
      ) : (
        <ul aria-label={TRANSFERS_HEADING} className="m-0 flex min-w-0 list-none flex-col p-0">
          {waiting.map((one) => (
            <li
              key={one.agent_id}
              className="flex min-w-0 flex-wrap items-center justify-between gap-2 border-b border-line py-2.5 first:pt-0 last:border-b-0 last:pb-0"
            >
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 text-[13px] font-medium text-ink">{one.display_name}</span>
                <Chip>{one.running ? RUNNING : STOPPED}</Chip>
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="min-h-11 sm:min-h-8"
                disabled={busy}
                aria-label={`${TAKE_ON} ${one.display_name}`}
                onClick={() => {
                  setFailure(null);
                  setChosen(one);
                }}
              >
                {TAKE_ON}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={chosen !== null}
        question={`Become the owner of ${chosen?.display_name ?? ""}?`}
        consequence={TAKE_ON_CONSEQUENCE}
        details={failure === null ? undefined : <FailureNotice failure={failure} title={NOT_TAKEN} />}
        confirmLabel={TAKE_ON}
        cancelLabel={KEEP_WAITING}
        busy={busy}
        onConfirm={() => {
          if (chosen !== null) {
            take(chosen);
          }
        }}
        onCancel={() => {
          setChosen(null);
          setFailure(null);
        }}
      />
    </SectionCard>
  );
}
