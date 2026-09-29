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
 * A reader who reaches no source and an install with none are one answer from the API and are drawn
 * alike, and nothing here counts rows the reader may not see. Identifiers are in `Advanced` only.
 *
 * **A staff list read through Connect Lark shows Lark's card here too**, with the same Test, Manage
 * and Disconnect as the Connectors screen (`connectors/LarkCard.tsx`), and Connect Lark is offered
 * only while Lark is not connected; once it is, the offer is adding the staff list to it.
 *
 * Task ids: M1.6.12, M1.8.6, M1.8.9, M27.7.2, M27.16.1
 */

import { useCallback, useState, type ReactNode } from "react";
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
  readTrial,
  RUNS_API_PATH,
  STAFF_SOURCES_API_PATH,
  STAFF_SOURCES_LABEL,
  TRANSFERS_API_PATH,
  TRIAL_API_PATH,
  wasRead,
  type Guides,
  type Read,
  type SyncRun,
  type TrialAnswer,
  type TrialRun,
} from "../staffSourcesQuery";
import { LARK_API_PATH, type LarkGuide } from "../larkConnectQuery";
import { LarkCard } from "../connectors/LarkCard";
import type { LarkStart } from "../connectors/LarkFlow";
import { LarkDialog } from "../connectors/SourceActs";
import { ACT_LABELS } from "../connectors/connectorActions";
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
export const READING = "Reading the source.";
export const CHANGES_NOTHING = "A run would change nothing.";
export const WOULD_ADD_LABEL = "People a run would add";
export const ABSENT_LABEL = "People the source did not list";
export const WOULD_REMOVE_LABEL = "People a run would remove";
export const WOULD_DEACTIVATE_LABEL = "People the source says have left";
export const WITHHELD_LABEL = "Why fewer people would be removed";
export const REFUSALS_LABEL = "What a run would refuse";
export const GAPS_LABEL = "What is wrong with this source";

export const RUNS_HEADING = "Recent sync runs";
export const RUNS_LEDE = "What each scheduled run changed. Somebody who leaves is marked, never deleted.";
export const NO_RUNS = "No sync has run yet.";
export const CHANGED_NOBODY = "This run changed nobody.";
export const RUN_ADDED_LABEL = "Added";
export const RUN_MARKED_LEFT_LABEL = "Marked as having left";
export const RUN_RENAMED_LABEL = "Address moved";
export const RUN_WITHHELD_LABEL = "Held back";

export const ADVANCED_SOURCE = "Source key";
export const ADVANCED_NEEDS = "Settings it needs";
export const ADVANCED_UNSET = "Settings still to set";
export const ADVANCED_SLOT = "Credential slot";
export const ADVANCED_AGENTS = "Agents waiting";
export const ADVANCED_ROLES = "Roles the last trial read proposed";

/** The trial: asked for when somebody presses the button, and never with the page. */
function useTrial(): {
  readonly busy: boolean;
  readonly failure: ApiFailure | null;
  readonly read: Read<TrialRun> | null;
  readonly run: () => void;
} {
  const [read, setRead] = useState<Read<TrialRun> | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const run = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<TrialAnswer>(TRIAL_API_PATH);
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setRead(readTrial(result.data));
    })();
  }, []);
  return { busy, failure, read, run };
}

/** What a trial read: a plan as lists of people, or why there is none. */
function TrialResult({ trial }: { readonly trial: ReturnType<typeof useTrial> }) {
  if (trial.busy) {
    return (
      <p role="status" className="m-0 text-[12.5px] text-dim">
        {READING}
      </p>
    );
  }
  if (trial.failure !== null) {
    return <FailureNotice failure={trial.failure} />;
  }
  if (trial.read === null) {
    return null;
  }
  if (!wasRead(trial.read)) {
    return <Note>{trial.read.unread}</Note>;
  }
  const plan = trial.read.panel.plan;
  if (plan === null || plan === undefined) {
    return (
      <div className="flex min-w-0 flex-col gap-1.5">
        {trial.read.panel.refusals.map((why) => (
          <Problem key={why}>{why}</Problem>
        ))}
      </div>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {plan.changes_nothing ? <Note>{CHANGES_NOTHING}</Note> : null}
      <Names label={REFUSALS_LABEL} names={plan.refusals} />
      <Names label={GAPS_LABEL} names={plan.gaps} />
      <Names
        label={WOULD_ADD_LABEL}
        names={plan.would_add.map((person) => (
          <span key={person.work_address} className="inline-flex min-w-0 flex-wrap items-center gap-1.5">
            <span>{person.display_name}</span>
            <span className="text-dim">{person.work_address}</span>
            {[person.department, ...person.groups]
              .filter((one) => one !== "")
              .map((one) => (
                <Chip key={one}>{one}</Chip>
              ))}
          </span>
        ))}
      />
      <Names label={ABSENT_LABEL} names={plan.absent} />
      <Names label={WOULD_REMOVE_LABEL} names={plan.would_remove} />
      <Names label={WITHHELD_LABEL} names={plan.withheld} />
      <Names label={WOULD_DEACTIVATE_LABEL} names={plan.would_deactivate} />
    </div>
  );
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
  const [lark, setLark] = useState<LarkStart | null>(null);
  const larkGuide = useResource<LarkGuide>(LARK_API_PATH, version).data;
  const larkStaff = larkGuide?.uses.find((one) => one.name === "staff_list");
  const page = useResource<unknown>(STAFF_SOURCES_API_PATH, version);
  const runsAnswer = useResource<unknown>(RUNS_API_PATH, version);
  const credentialAnswer = useResource<unknown>(CREDENTIAL_API_PATH, version);
  const transfersAnswer = useResource<unknown>(TRANSFERS_API_PATH, version);
  const guides = readGuides(useResource<unknown>(GUIDES_API_PATH).data);
  const trial = useTrial();

  // After every write: say what the API said, and read everything again.
  const done = useCallback((sentence: string) => {
    setTold(sentence);
    setVersion((one) => one + 1);
  }, []);

  const body = readStaffSources(page.data);
  const selection = body.selection ?? null;
  const chosen = body.options.find((one) => one.chosen);
  const runs = readRuns(runsAnswer.data);
  const last = runs[0];
  // Left out for a reader the API does not answer, whatever the reason.
  const credential = readCredential(credentialAnswer.data);
  const waiting = readTransfers(transfersAnswer.data);
  const title = selection === null ? NONE_CHOSEN : sourceTitle(selection.name, guides);
  const trialRun = trial.read !== null && wasRead(trial.read) ? trial.read.panel : null;
  const roles = [
    ...(trialRun?.plan?.role_grants_to_add ?? []).map((one) => `Add ${one.role} to ${one.principal_id}, from ${one.source_group}`),
    ...(trialRun?.plan?.role_grants_to_remove ?? []).map(
      (one) => `Remove ${one.role} from ${one.principal_id}, from ${one.source_group}`,
    ),
  ];

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
              disabled={trial.busy}
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
            <TrialResult trial={trial} />
          </div>
        </SectionCard>

        {larkGuide !== null && larkStaff?.switched_on === true ? (
          <LarkCard guide={larkGuide} onOpen={setLark} onDone={done} staffSourcesLink={false} />
        ) : null}

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
            {roles.length === 0 ? null : (
              <Fact label={ADVANCED_ROLES}>
                <Names label={ADVANCED_ROLES} names={roles} />
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

  // Offered to a reader who may switch Lark's staff list on, until it is on; the card then has it.
  const larkAction =
    larkGuide === null || larkStaff === undefined || larkStaff.switched_on || !larkStaff.may_switch_on ? undefined : (
      <Button
        variant="outline"
        className="min-h-11 sm:min-h-8"
        onClick={() => {
          setLark({ at: "choose", add: ["staff_list"] });
        }}
      >
        {larkGuide.connected ? ACT_LABELS.addLarkUse : ACT_LABELS.connectLark}
      </Button>
    );

  return (
    <div data-slot="staff-sources-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: STAFF_SOURCES_HEADING }]}
        title={STAFF_SOURCES_HEADING}
        lede={STAFF_SOURCES_LEDE}
        primary={primary}
        actions={larkAction}
      />
      {told === "" ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      {content}
      {lark === null ? null : (
        <LarkDialog
          start={lark}
          onClose={() => {
            setLark(null);
            setVersion((one) => one + 1);
          }}
          onDone={(sentence) => {
            setLark(null);
            done(sentence);
          }}
        />
      )}
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
