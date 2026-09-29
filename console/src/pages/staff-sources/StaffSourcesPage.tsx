/**
 * Staff sources: which list of people this install reads, whether it can read it, and the acts that
 * change that. The owner asked for a clean status page with connect, switch and the credential.
 *
 * The status comes first as three facts: the source in use, the last sync and its outcome, and
 * whether the sync credential is held. Below it, the source with a read that changes nothing, the
 * credential, the recent runs and the agents waiting for an owner. Connecting or switching is a
 * drawer. Every act that changes something is confirmed through the kit's `ConfirmDialog`, and after
 * every write the page reads everything again rather than patching what it drew.
 *
 * **Try a read asks the worker, and its answer is a run.** Since 2026-09-29 the button posts to the
 * trial's address, the worker reads the source with the credential the night's run uses and applies
 * nothing, and what it read arrives under Recent sync runs as a trial read. Until then the button
 * showed "This install cannot try your staff source yet. Nothing here fetches a list", which had not
 * been true since the nightly sync began reading one. The page asks whether the read is still
 * waiting every few seconds, a bounded number of times, and reads the runs again when it is not.
 *
 * **Each run says what it read, in counts**: departments read and named, people read and placed,
 * why anybody is in no department and what to change at the source. On 2026-09-29 a Lark sync placed
 * 123 people nowhere and its row said "applied". These are the one figures on this screen and they
 * are not a count of anything a reader was not shown: a run is answered whole or not at all.
 *
 * A reader who reaches no source and an install with none are one answer from the API and are drawn
 * alike, and nothing here counts rows the reader may not see. Identifiers are in `Advanced` only.
 *
 * Task ids: M1.6.12, M1.8.6, M1.8.9, M27.7.2, M27.16.1
 */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
  StatCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  CREDENTIAL_API_PATH,
  GUIDES_API_PATH,
  readCredential,
  readGuides,
  readRuns,
  readStaffSources,
  readTransfers,
  readStaffTrial,
  RUNS_API_PATH,
  STAFF_SOURCES_API_PATH,
  STAFF_SOURCES_LABEL,
  TRANSFERS_API_PATH,
  TRIAL_API_PATH,
  TRIAL_POLL_MS,
  TRIAL_POLLS,
  TRIED,
  type Guides,
  type SyncRun,
} from "../staffSourcesQuery";
import { ConnectDrawer } from "./ConnectDrawer";
import { Names, Problem } from "./parts";
import { outcomeWords, sourceTitle, when } from "./staffSourceWords";
import { SyncCredential } from "./SyncCredential";
import { Transfers } from "./Transfers";

export const STAFF_SOURCES_HEADING = STAFF_SOURCES_LABEL;
export const STAFF_SOURCES_LEDE =
  "Where this install reads who works here and which department they are in. A staff list never signs anybody in.";
export const LOADING = "Loading staff sources.";

export const AT_A_GLANCE = "The staff source at a glance";
export const SOURCE_IN_USE = "Source in use";
export const LAST_SYNC = "Last sync";
export const SYNC_CREDENTIAL = "Sync credential";
export const NONE_CHOSEN = "None chosen";
export const NO_RUN_YET = "No run yet";
export const READY = "Ready to read";
export const NOT_READY = "Not ready";
export const HELD = "Held";
export const NOT_HELD = "Not held";
export const NOT_KNOWN = "Not known";

export const CONNECT_A_SOURCE = "Connect a source";
export const SWITCH_SOURCE = "Switch source";
export const HOW_TO_CONNECT = "How to connect";

export const SOURCE_HEADING = "Staff source";
export const SOURCE_LEDE = "The list this install reads. A trial read changes nothing.";
export const SOURCE_LABEL = "Source";
export const MEANING_LABEL = "What it means";
export const NO_SOURCE = "No staff source to show.";
export const TRY_A_READ = "Try a read";
export const ASKING = "Asking the worker to read the source.";
export const TRIAL_READ =
  "The worker has read your staff source and changed nobody. What it read is the newest trial read under Recent sync runs.";
export const TRIAL_NOT_YET =
  "The worker has not read the source yet. When it does, what it read appears under Recent sync runs as a trial read.";

export const RUNS_HEADING = "Recent sync runs";
export const RUNS_LEDE = "What each scheduled run changed. Somebody who leaves is marked, never deleted.";
export const NO_RUNS = "No sync has run yet.";
export const CHANGED_NOBODY = "This run changed nobody.";
export const RUN_ADDED_LABEL = "Added";
export const RUN_MARKED_LEFT_LABEL = "Marked as having left";
export const RUN_RENAMED_LABEL = "Address moved";
export const RUN_WITHHELD_LABEL = "Held back";
export const RUN_REPORT_LABEL = "What was read";

export const ADVANCED_SOURCE = "Source key";
export const ADVANCED_NEEDS = "Settings it needs";
export const ADVANCED_UNSET = "Settings still to set";
export const ADVANCED_SLOT = "Credential slot";
export const ADVANCED_AGENTS = "Agents waiting";

/** Where a trial stands on this page: never asked, being asked, waiting for the worker, or read. */
type TrialState =
  | { readonly kind: "idle" }
  | { readonly kind: "asking" }
  | { readonly kind: "waiting"; readonly told: string; readonly polls: number }
  | { readonly kind: "read" }
  | { readonly kind: "not_yet" };

/**
 * The trial: asked for when somebody presses the button, and never with the page. While the worker
 * has not read, the page asks the trial's address whether it still waits, every `TRIAL_POLL_MS`, at
 * most `TRIAL_POLLS` times, and calls `onRead` once it does not so the runs are read again.
 */
function useTrial(onRead: () => void): {
  readonly state: TrialState;
  readonly failure: ApiFailure | null;
  readonly run: () => void;
} {
  const [state, setState] = useState<TrialState>({ kind: "idle" });
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const run = useCallback(() => {
    setState({ kind: "asking" });
    void (async () => {
      const result = await request<unknown>(TRIAL_API_PATH, { method: "POST", body: {} });
      if (!result.ok) {
        setFailure(result.failure);
        setState({ kind: "idle" });
        return;
      }
      setFailure(null);
      const asked = readStaffTrial(result.data);
      setState({ kind: "waiting", told: asked.told, polls: 0 });
    })();
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
        const result = await request<unknown>(TRIAL_API_PATH);
        if (result.ok && !readStaffTrial(result.data).waiting) {
          setState({ kind: "read" });
          onRead();
          return;
        }
        setState({ kind: "waiting", told, polls: polls + 1 });
      })();
    }, TRIAL_POLL_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [polls, told, onRead]);
  return { state, failure, run };
}

/** Where the trial stands, in words. What it read is a run, drawn with the others. */
function TrialStatus({ trial }: { readonly trial: ReturnType<typeof useTrial> }) {
  if (trial.failure !== null) {
    return <FailureNotice failure={trial.failure} />;
  }
  switch (trial.state.kind) {
    case "asking":
      return (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {ASKING}
        </p>
      );
    case "waiting":
      return (
        <div role="status">
          <Note>{trial.state.told}</Note>
        </div>
      );
    case "read":
      return (
        <div role="status">
          <Note kind="done">{TRIAL_READ}</Note>
        </div>
      );
    case "not_yet":
      return <Note>{TRIAL_NOT_YET}</Note>;
    default:
      return null;
  }
}

/** One scheduled run: when, what came of it, the API's sentence, and who it changed by name. */
function Run({ run, guides }: { readonly run: SyncRun; readonly guides: Guides | null }) {
  return (
    <li className="flex min-w-0 flex-col gap-2 border-b border-line py-3 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <time dateTime={run.finished_at} className="text-[13px] font-medium text-ink">
          {when(run.finished_at)}
        </time>
        <Chip>{sourceTitle(run.source, guides)}</Chip>
        <Chip>{outcomeWords(run.outcome)}</Chip>
      </div>
      {run.detail === "" ? null : <p className="m-0 text-[12.5px] leading-snug text-dim">{run.detail}</p>}
      {run.changed_nobody ? <Note>{CHANGED_NOBODY}</Note> : null}
      {/* An API from before `0155` sends no report, which is drawn as nothing. */}
      <Names label={RUN_REPORT_LABEL} names={run.report ?? []} />
      <Names label={RUN_ADDED_LABEL} names={run.added} />
      <Names label={RUN_MARKED_LEFT_LABEL} names={run.marked_left} />
      <Names label={RUN_RENAMED_LABEL} names={run.renamed} />
      <Names label={RUN_WITHHELD_LABEL} names={run.withheld} />
    </li>
  );
}

export function StaffSourcesPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState("");
  const [connecting, setConnecting] = useState(false);
  const page = useResource<unknown>(STAFF_SOURCES_API_PATH, version);
  const runsAnswer = useResource<unknown>(RUNS_API_PATH, version);
  const credentialAnswer = useResource<unknown>(CREDENTIAL_API_PATH, version);
  const transfersAnswer = useResource<unknown>(TRANSFERS_API_PATH, version);
  const guides = readGuides(useResource<unknown>(GUIDES_API_PATH).data);

  // After every write: say what the API said, and read everything again.
  const done = useCallback((sentence: string) => {
    setTold(sentence);
    setVersion((one) => one + 1);
  }, []);
  // After the worker has read a trial: read everything again, so the trial's run is drawn.
  const reread = useCallback(() => {
    setVersion((one) => one + 1);
  }, []);
  const trial = useTrial(reread);

  const body = readStaffSources(page.data);
  const selection = body.selection ?? null;
  const chosen = body.options.find((one) => one.chosen);
  const runs = readRuns(runsAnswer.data);
  // A trial read is not a sync, so the status's last sync is the newest run that was one.
  const last = runs.find((one) => one.outcome !== TRIED);
  // Left out for a reader the API does not answer, whatever the reason.
  const credential = readCredential(credentialAnswer.data);
  const waiting = readTransfers(transfersAnswer.data);
  const title = selection === null ? NONE_CHOSEN : sourceTitle(selection.name, guides);
  const pending = trial.state.kind === "asking" || trial.state.kind === "waiting";

  let content: ReactNode;
  if (page.failure !== null) {
    content = <FailureState failure={page.failure} />;
  } else if (page.busy || runsAnswer.busy || credentialAnswer.busy || transfersAnswer.busy) {
    content = <LoadingState label={LOADING} />;
  } else {
    content = (
      <>
        <KpiStrip label={AT_A_GLANCE} count={credential === null ? 2 : 3}>
          <StatCard
            label={SOURCE_IN_USE}
            value={title}
            sub={selection === null || !selection.reads_a_list ? undefined : selection.ready ? READY : NOT_READY}
          />
          <StatCard
            label={LAST_SYNC}
            value={runsAnswer.failure !== null ? undefined : last === undefined ? NO_RUN_YET : when(last.finished_at)}
            sub={last === undefined ? undefined : outcomeWords(last.outcome)}
          />
          {credential === null ? null : (
            <StatCard
              label={SYNC_CREDENTIAL}
              value={credential.held === true ? HELD : credential.held === false ? NOT_HELD : NOT_KNOWN}
              sub={
                credential.set_at === null || credential.set_at === undefined
                  ? undefined
                  : `Written ${when(credential.set_at)}`
              }
            />
          )}
        </KpiStrip>

        <SectionCard
          title={SOURCE_HEADING}
          lede={SOURCE_LEDE}
          action={
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              disabled={pending}
              onClick={trial.run}
            >
              {TRY_A_READ}
            </Button>
          }
        >
          <div className="flex min-w-0 flex-col gap-3">
            {selection === null ? (
              <p className="m-0 text-[13px] text-dim">{NO_SOURCE}</p>
            ) : (
              <FactList>
                <Fact label={SOURCE_LABEL}>{title}</Fact>
                {selection.meaning === "" ? null : <Fact label={MEANING_LABEL}>{selection.meaning}</Fact>}
              </FactList>
            )}
            {selection === null || selection.ready || selection.refusal === "" ? null : (
              <Problem>{selection.refusal}</Problem>
            )}
            <TrialStatus trial={trial} />
          </div>
        </SectionCard>

        {credential === null ? null : <SyncCredential credential={credential} onDone={done} />}

        <SectionCard title={RUNS_HEADING} lede={RUNS_LEDE}>
          {runsAnswer.failure !== null ? (
            <FailureState failure={runsAnswer.failure} />
          ) : runs.length === 0 ? (
            <p className="m-0 text-[13px] text-dim">{NO_RUNS}</p>
          ) : (
            <ul aria-label={RUNS_HEADING} className="m-0 flex min-w-0 list-none flex-col p-0">
              {runs.map((run) => (
                <Run key={`${run.source} ${run.finished_at}`} run={run} guides={guides} />
              ))}
            </ul>
          )}
        </SectionCard>

        {transfersAnswer.failure !== null ? (
          <FailureState failure={transfersAnswer.failure} />
        ) : (
          <Transfers waiting={waiting} onDone={done} />
        )}

        <Advanced>
          <FactList>
            {selection === null ? null : (
              <Fact label={ADVANCED_SOURCE}>
                <Chip mono>{selection.name}</Chip>
              </Fact>
            )}
            {chosen === undefined || chosen.needs.length === 0 ? null : (
              <Fact label={ADVANCED_NEEDS}>
                <span className="flex flex-wrap gap-1.5">
                  {chosen.needs.map((name) => (
                    <Chip key={name} mono>
                      {name}
                    </Chip>
                  ))}
                </span>
              </Fact>
            )}
            {selection === null || selection.unsupplied.length === 0 ? null : (
              <Fact label={ADVANCED_UNSET}>
                <span className="flex flex-wrap gap-1.5">
                  {selection.unsupplied.map((name) => (
                    <Chip key={name} mono>
                      {name}
                    </Chip>
                  ))}
                </span>
              </Fact>
            )}
            {credential === null ? null : (
              <Fact label={ADVANCED_SLOT}>
                <Chip mono>{credential.slot}</Chip>
              </Fact>
            )}
            {waiting.length === 0 ? null : (
              <Fact label={ADVANCED_AGENTS}>
                <Names
                  label={ADVANCED_AGENTS}
                  names={waiting.map((one) => `${one.display_name}: ${one.agent_id}, owned by ${one.owner_id}`)}
                />
              </Fact>
            )}
          </FactList>
        </Advanced>
      </>
    );
  }

  const primary =
    guides === null ? undefined : (
      <Button
        variant={guides.may_connect ? "default" : "outline"}
        className="min-h-11 sm:min-h-8"
        onClick={() => {
          setConnecting(true);
        }}
      >
        {!guides.may_connect
          ? HOW_TO_CONNECT
          : selection !== null && selection.reads_a_list
            ? SWITCH_SOURCE
            : CONNECT_A_SOURCE}
      </Button>
    );

  return (
    <div data-slot="staff-sources-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: STAFF_SOURCES_HEADING }]} title={STAFF_SOURCES_HEADING} lede={STAFF_SOURCES_LEDE} primary={primary} />
      {told === "" ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      {content}
      {connecting ? (
        <ConnectDrawer
          onClose={() => {
            setConnecting(false);
          }}
          onConnected={done}
        />
      ) : null}
    </div>
  );
}
