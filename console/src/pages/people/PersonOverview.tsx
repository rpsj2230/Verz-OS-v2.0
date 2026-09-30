/**
 * A person's Overview: who they are, where they sit, and the agents they steward, with the one act a
 * leaver's agent needs, taking it on.
 *
 * **The agents are the roster's, filtered to this steward** (M27.15.18, M27.15.5): what the Agents
 * list would show this reader for that owner, so an agent this reader may not open is not here and
 * nothing says it was left out. Each is handed on to a new steward through the Agents pages' own
 * act (`agents/LifecycleActs`), which asks the lifecycle route what this reader may do and confirms.
 * A leaver's agent this reader may take on is the staff source's transfers answer, and taking it on
 * is that route, confirmed: the reader becomes its steward and its ceiling does not move.
 *
 * **Edits of a person are not offered**, because the name, the department and the employment come
 * from the staff source and a local edit would be overwritten by the next sync. That is a sentence,
 * not a disabled control.
 *
 * **What the staff list says about them**: their status and employment type, and, when the list keeps
 * them from signing in or asking, why, in the API's words (M1.6.13, M1.6.14).
 *
 * Task ids: M27.11.2, M27.15.18, M27.16.1, M1.6.13, M1.6.14
 */

import { Bot } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  ConfirmDialog,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  NotOffered,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { agentAddress } from "../agents/AgentsPage";
import { StatePill } from "../agents/pills";
import { dayWords } from "../access/formParts";
import { EDITED_AT_THE_SOURCE } from "./peopleActions";
import { useLifecycleActs } from "../agents/LifecycleActs";
import { SecondFactorPill, StaffStatusPill, StandingPill } from "./pills";
import {
  AGENTS_API_PATH,
  EMPLOYMENT_TYPE_WORDS,
  TRANSFERS_API_PATH,
  aboutPerson,
  readOwnedAgents,
  readWaiting,
  transferApiPath,
  type PersonDetail,
  type Waiting,
} from "./peopleQuery";

export const ABOUT_HEADING = "About";
export const STEWARDS_HEADING = "Agents they steward";
export const NO_AGENTS_STEWARDED = "No agent you may open has them as its steward.";
export const TAKE_ON = "Take it on";
export const HAND_ON = "Hand on";

/** The Agents list, which pages, searches and filters the roster this card borrows. */
export const AGENTS_ADDRESS = "/agents";

export function takeOnQuestion(agent: string): string {
  return `Become the steward of ${agent}?`;
}

export const TAKING_ON_DOES =
  "You become its steward and it starts again if it had stopped. What it may reach does not change, and the change is recorded in the audit trail.";

function TakeOn({ waiting, onTaken }: { readonly waiting: Waiting; readonly onTaken: () => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const take = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(transferApiPath(waiting.agentId), { method: "POST" });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onTaken();
    })();
  }, [waiting.agentId, onTaken]);
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          setAsking(true);
        }}
      >
        {TAKE_ON}
      </Button>
      {failure === null ? null : <FailureState failure={failure} />}
      <ConfirmDialog
        open={asking}
        question={takeOnQuestion(waiting.displayName)}
        consequence={TAKING_ON_DOES}
        confirmLabel={TAKE_ON}
        cancelLabel="Leave it"
        busy={busy}
        onConfirm={take}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </>
  );
}

function Stewarded({ principalId }: { readonly principalId: string }) {
  const [version, setVersion] = useState(0);
  const moved = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  // The Agents pages' own hand-over, asked of the lifecycle route and confirmed there.
  const lifecycle = useLifecycleActs(moved, agentAddress);
  const agents = useResource<unknown>(aboutPerson(AGENTS_API_PATH, "owner_id", principalId), version);
  const transfers = useResource<unknown>(TRANSFERS_API_PATH, version);
  const owned = readOwnedAgents(agents.data, principalId);
  const waiting = readWaiting(transfers.data, principalId);
  const taken = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);

  let body;
  if (agents.failure !== null) {
    body = <FailureState failure={agents.failure} />;
  } else if (agents.data === null) {
    body = <LoadingState label="Loading the agents they steward." rows={2} />;
  } else if (owned.length === 0 && waiting.length === 0) {
    body = <p className="m-0 text-[13px] text-dim">{NO_AGENTS_STEWARDED}</p>;
  } else {
    body = (
      <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
        {owned.map((one) => (
          <li key={one.agentId} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="flex min-w-0 items-center gap-2">
              <Bot aria-hidden className="size-4 shrink-0 text-dim" />
              <Link to={agentAddress(one.agentId)} className="font-medium text-ink underline-offset-4 hover:underline [overflow-wrap:anywhere]">
                {one.displayName}
              </Link>
              {one.state === undefined ? null : <StatePill state={one.state} />}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={lifecycle.busy}
              aria-label={`Hand ${one.displayName} on to a new steward`}
              onClick={() => {
                lifecycle.choose(one.agentId, "transfer");
              }}
            >
              {HAND_ON}
            </Button>
          </li>
        ))}
        {waiting.map((one) => (
          <li key={`waiting-${one.agentId}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="flex min-w-0 flex-col">
              <span className="font-medium text-ink [overflow-wrap:anywhere]">{one.displayName}</span>
              <span className="text-[12px] text-dim">
                {one.running ? "Waiting for a new steward, still running." : "Waiting for a new steward, stopped."}
              </span>
            </span>
            <TakeOn waiting={one} onTaken={taken} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <SectionCard
      title={STEWARDS_HEADING}
      lede="An agent's steward answers for it. A leaver's agents wait here for somebody to take them on."
      action={
        <>
          <Link to={AGENTS_ADDRESS} className="text-[12.5px] text-acc-text underline-offset-4 hover:underline">
            All agents
          </Link>
        </>
      }
    >
      {lifecycle.notice}
      {body}
      {lifecycle.dialog}
    </SectionCard>
  );
}

export function PersonOverview({ detail }: { readonly detail: PersonDetail }) {
  const { person, placements } = detail;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title={ABOUT_HEADING} footer={<NotOffered>{EDITED_AT_THE_SOURCE}</NotOffered>}>
        {detail.keptOut === undefined ? null : <Note kind="not-yet">{detail.keptOut}</Note>}
        <FactList>
          <Fact label="Department">{placements.department?.name ?? person.departmentName ?? person.department ?? "Not placed"}</Fact>
          {placements.teams.length === 0 ? null : <Fact label="Teams">{placements.teams.map((one) => one.name).join(", ")}</Fact>}
          {placements.leads.length === 0 ? null : <Fact label="Leads">{placements.leads.map((one) => one.name).join(", ")}</Fact>}
          {person.employment === undefined ? null : <Fact label="Employment"><span className="capitalize">{person.employment}</span></Fact>}
          {person.staffStatus === undefined ? null : (
            <Fact label="On the staff list">
              <StaffStatusPill status={person.staffStatus} />
            </Fact>
          )}
          {person.employmentType === undefined ? null : (
            <Fact label="Employment type">{EMPLOYMENT_TYPE_WORDS[person.employmentType] ?? person.employmentType}</Fact>
          )}
          <Fact label="Standing">
            <StandingPill standing={person.standing} />
          </Fact>
          {person.lastSignedInAt === undefined ? null : <Fact label="Last sign-in">{dayWords(person.lastSignedInAt)}</Fact>}
          {person.secondFactor === undefined ? null : (
            <Fact label="Second factor">
              <SecondFactorPill seen={person.secondFactor} />
            </Fact>
          )}
        </FactList>
      </SectionCard>
      <Stewarded principalId={person.principalId} />
      <Advanced>
        <FactList>
          <Fact label="Person id">
            <code className="font-mono text-[12px]">{person.principalId}</code>
          </Fact>
          {person.department === undefined ? null : (
            <Fact label="Department short name">
              <code className="font-mono text-[12px]">{person.department}</code>
            </Fact>
          )}
        </FactList>
      </Advanced>
    </div>
  );
}
