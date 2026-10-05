/**
 * Sync now, beside the scheduled staff sync: when it last ran, when it next runs, and a button that
 * asks the worker for that same run at once (`brain.staff_source_routes.SYNC_PATH`). The owner asked
 * for it on 2026-09-30, after the scheduled run was the only way to see a change to the staff list.
 *
 * **It asks the worker for the scheduled run and does not run anything itself**, so the run is the
 * one the schedule makes, recorded under Recent sync runs like any other, one at a time, and a
 * second press asks for one run. While the worker has not started, the section asks whether it
 * still waits every `TRIAL_POLL_MS`, at most `TRIAL_POLLS` times, as the trial does; once it has
 * run, the page reads everything again and this says what the newest run did, in the run's own
 * sentence.
 *
 * Drawn only for a reader the API lets press it (`may_sync`), and confirmed first, because it applies
 * the list. **The page draws it outside the part it replaces with a loading state**, because the page
 * reads everything again once the run is done and a section inside that part would be unmounted, and
 * forget it was waiting, at exactly the moment it has something to say.
 *
 * Task ids: M1.10.2
 */

import { useCallback, useEffect, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Fact, FactList, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { readSyncNow, SYNC_API_PATH, TRIAL_POLL_MS, TRIAL_POLLS, type SyncRun } from "../staffSourcesQuery";
import { when } from "./staffSourceWords";

export const SYNC_HEADING = "Scheduled sync";
export const SYNC_LEDE =
  "The staff sync runs once a day. Sync now runs it straight away, with the same credential, and it is recorded like a scheduled run.";
export const SYNC_NOW = "Sync now";
export const SYNC_QUESTION = "Run the staff sync now?";
export const SYNC_CONSEQUENCE =
  "The worker reads the staff list and applies it now: people who joined are added, people who left are marked, and each active person is on People.";
export const NOT_NOW = "Not now";
export const LAST_RUN = "Last run";
export const NEXT_RUN = "Next scheduled run";
export const NEVER_RUN = "Not run yet";
export const AT_NEXT_TICK = "Within a minute";
export const SYNC_NOT_ASKED = "Sync now was not asked";
export const SYNC_DONE = "The staff sync has run. What it did:";
export const SYNC_NOT_YET =
  "The worker has not started the run yet. When it does, what it did appears under Recent sync runs.";

type SyncState =
  | { readonly kind: "idle" }
  | { readonly kind: "asking" }
  | { readonly kind: "waiting"; readonly told: string; readonly polls: number }
  | { readonly kind: "done" }
  | { readonly kind: "not_yet" };

export function SyncNow({
  version,
  latest,
  onRun,
}: {
  readonly version: number;
  /** The newest run that was not a trial read, whose sentence is what a finished Sync now did. */
  readonly latest: SyncRun | undefined;
  /** Called once the worker has run, so the page reads its runs again. */
  readonly onRun: () => void;
}) {
  const answer = useResource<unknown>(SYNC_API_PATH, version);
  const view = readSyncNow(answer.data);
  const [state, setState] = useState<SyncState>({ kind: "idle" });
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const ask = useCallback(() => {
    setState({ kind: "asking" });
    void (async () => {
      const result = await request<unknown>(SYNC_API_PATH, { method: "POST", body: {} });
      if (!result.ok) {
        setFailure(result.failure);
        setState({ kind: "idle" });
        return;
      }
      setFailure(null);
      setConfirming(false);
      setState({ kind: "waiting", told: readSyncNow(result.data).told, polls: 0 });
    })();
  }, []);
  const confirm = useCallback((open: boolean) => {
    setFailure(null);
    setConfirming(open);
  }, []);

  const polls = state.kind === "waiting" ? state.polls : -1;
  const told = state.kind === "waiting" ? state.told : "";
  useEffect(() => {
    if (polls < 0) {
      return undefined;
    }
    if (polls >= TRIAL_POLLS) {
      setState({ kind: "not_yet" });
      return undefined;
    }
    const timer = setTimeout(() => {
      void (async () => {
        const result = await request<unknown>(SYNC_API_PATH);
        if (result.ok && !readSyncNow(result.data).waiting) {
          setState({ kind: "done" });
          onRun();
          return;
        }
        setState({ kind: "waiting", told, polls: polls + 1 });
      })();
    }, TRIAL_POLL_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [polls, told, onRun]);

  if (!view.may_sync) {
    return null;
  }
  const pending = state.kind === "asking" || state.kind === "waiting";
  return (
    <SectionCard
      title={SYNC_HEADING}
      lede={SYNC_LEDE}
      action={
        <Button
          type="button"
          size="sm"
          className="min-h-11 sm:min-h-8"
          disabled={pending}
          onClick={() => {
            confirm(true);
          }}
        >
          {SYNC_NOW}
        </Button>
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        <FactList>
          <Fact label={LAST_RUN}>{view.last_run_at === null ? NEVER_RUN : when(view.last_run_at)}</Fact>
          <Fact label={NEXT_RUN}>{view.next_run_at === null ? AT_NEXT_TICK : when(view.next_run_at)}</Fact>
        </FactList>
        {state.kind === "waiting" ? (
          <div role="status">
            <Note>{state.told}</Note>
          </div>
        ) : null}
        {state.kind === "not_yet" ? <Note>{SYNC_NOT_YET}</Note> : null}
        {state.kind === "done" && latest !== undefined ? (
          <div role="status">
            <Note kind="done">
              {SYNC_DONE} {latest.detail}
              {(latest.report ?? []).length === 0 ? null : ` ${(latest.report ?? []).join(" ")}`}
            </Note>
          </div>
        ) : null}
      </div>
      <ConfirmDialog
        open={confirming}
        question={SYNC_QUESTION}
        consequence={SYNC_CONSEQUENCE}
        details={failure === null ? undefined : <FailureNotice failure={failure} title={SYNC_NOT_ASKED} />}
        confirmLabel={SYNC_NOW}
        cancelLabel={NOT_NOW}
        busy={state.kind === "asking"}
        onConfirm={ask}
        onCancel={() => {
          confirm(false);
        }}
      />
    </SectionCard>
  );
}
