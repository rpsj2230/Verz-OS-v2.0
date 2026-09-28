/**
 * The Profile view of one skill: every version with its words, what it may reach and what changed,
 * the agents running it, its categories, and every act on it.
 *
 * **Every act whose route exists is a live control, and every one that changes something is
 * confirmed.** Approve and Reject (a decision by the person who added it is recorded as theirs),
 * Retire and Reinstate a version, Assign it to an agent and Detach it from one each open a
 * `ConfirmDialog` saying what happens and to what, and only its confirm sends the write. Editing
 * saves a new version beside this one and changes nothing, so it is a form. Trying a skill out has
 * no route and is drawn inert with its sentence (`skillActions.ts`).
 *
 * **Retiring lists and never removes.** The answer to a retirement names the agents still running
 * the version among those this reader may see, and each keeps it until somebody detaches it here
 * (M27.15.56). **Detaching ends an assignment by adding a record**, and the agents list is read
 * again after it, so the agent is gone from it (M27.15.55).
 *
 * **Names on the page, identifiers in Advanced.** The version's digest, the commit it came from,
 * the version it was edited from and the people's identifiers are in each version's Advanced
 * section; the page names people and agents.
 *
 * Task ids: M27.16.1, M27.15.55, M27.15.56, M12.2.6, M12.3.2, M12.4.6
 */

import { FlaskConical, Pencil } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import {
  Advanced,
  Chip,
  ConfirmDialog,
  Fact,
  FactList,
  Note,
  SectionCard,
  UnavailableAction,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  decidedSentence,
  decisionConsequence,
  decisionQuestion,
  decisionWords,
  detachPath,
  reinstatementPath,
  retirementPath,
  reviewPath,
  sourceWords,
  type AgentChoice,
  type Detached,
  type LibrarySkill,
  type Retired,
  type SkillDiff,
  type SkillPin,
} from "../skillsQuery";
import { AssignForm, CategoriesForm, EditVersionForm, type Tell } from "./SkillForms";
import { ReviewPill, RetiredPill } from "./pills";
import { UNAVAILABLE } from "./skillActions";
import { dayWords, named, type SkillDetail } from "./skillDetailQuery";

export const VERSIONS_HEADING = "Versions";
export const AGENTS_HEADING = "Agents using it";
export const CATEGORIES_HEADING = "Categories";
export const NO_AGENTS = "No agent you can see runs this skill.";
export const VERSIONS_DIFFER = "These agents run different versions of this skill.";
export const REACH_LEDE =
  "It can use a tool it names only through an agent allowed that tool, for somebody who already holds what the tool needs.";
export const NOT_ON_THIS_INSTALL = "not a tool this install has";
export const NO_REGISTRY = "No tool list is loaded on the server, so what each tool needs cannot be shown.";
export const APPROVE = "Approve";
export const REJECT = "Reject";
export const KEEP_IT = "Leave it undecided";
export const RETIRE = "Retire version";
export const REINSTATE = "Reinstate version";
export const KEEP = "Keep as it is";
export const DETACH = "Detach";
export const DO_NOT_DETACH = "Keep it on the agent";
export const TRY_OUT = "Try it out";

export function retireQuestion(one: LibrarySkill): string {
  return `Retire ${one.name} ${one.version}?`;
}

export const RETIRE_CONSEQUENCE =
  "No agent can be given this version from now on. Agents already running it keep it until you detach " +
  "them, one at a time, below. The version stays in the library with its history, and you can reinstate it.";

export function reinstateQuestion(one: LibrarySkill): string {
  return `Reinstate ${one.name} ${one.version}?`;
}

export const REINSTATE_CONSEQUENCE = "This version can be assigned to agents again. Both changes stay in the history.";

export function detachQuestion(name: string, agent: string): string {
  return `Detach ${name} from ${agent}?`;
}

export function detachConsequence(agent: string): string {
  return (
    `${agent} stops using it from its next request. The assignment stays in the history, and the skill ` +
    "can be assigned to it again."
  );
}

export function retiredSentence(done: Retired): string {
  if (!done.retired) {
    return `${done.name} ${done.version} is reinstated and can be assigned again.`;
  }
  const still = done.holding.map((one) => one.display_name);
  return still.length === 0
    ? `${done.name} ${done.version} is retired. No agent you can see runs it.`
    : `${done.name} ${done.version} is retired. Still running it until you detach it: ${still.join(", ")}.`;
}

export function detachedSentence(done: Detached, agent: string): string {
  return `${done.skill_name} was detached from ${agent}.`;
}

function Changed({ diff }: { readonly diff: SkillDiff }) {
  const marks = { kept: "  ", removed: "- ", added: "+ " } as const;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <h4 className="m-0 text-[12.5px] font-semibold text-ink">What changed since version {diff.against_version}</h4>
      {diff.fields.length === 0 ? null : (
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[12.5px]">
          {diff.fields.map((change) => (
            <li key={change.field} className="[overflow-wrap:anywhere]">
              <span className="font-mono text-dim">{change.field}</span>: <del>{change.before}</del> <ins>{change.after}</ins>
            </li>
          ))}
        </ul>
      )}
      {/* Each line says what happened to it in its text, and del and ins say it to an eye and a
          screen reader alike, so no colour is needed. */}
      <pre className="m-0 max-h-72 overflow-auto rounded-md border border-line bg-sunk p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-body">
        {diff.body.map((line, index) => {
          const key = `${String(index)}-${line.change}`;
          const text = `${marks[line.change]}${line.text}\n`;
          if (line.change === "removed") {
            return <del key={key}>{text}</del>;
          }
          if (line.change === "added") {
            return <ins key={key}>{text}</ins>;
          }
          return <span key={key}>{text}</span>;
        })}
      </pre>
    </div>
  );
}

function Reach({ one, registryIsAbsent }: { readonly one: LibrarySkill; readonly registryIsAbsent: boolean }) {
  if (one.tools.length === 0) {
    return <span className="text-dim">It names no tools, so it can use none.</span>;
  }
  return (
    <span className="flex flex-col gap-1.5">
      <span className="flex flex-wrap gap-1">
        {one.tools.map((tool) =>
          tool.capability === null ? (
            <Chip key={tool.name} mono tone="requested">
              {tool.name} ({NOT_ON_THIS_INSTALL})
            </Chip>
          ) : (
            <Chip key={tool.name} mono>
              {tool.name} needs {tool.capability}
            </Chip>
          ),
        )}
      </span>
      {registryIsAbsent ? <span className="text-[12px] text-dim">{NO_REGISTRY}</span> : null}
    </span>
  );
}

/** Approve or Reject, each confirmed. */
function Decide({ one, onTold }: { readonly one: LibrarySkill; readonly onTold: Tell }) {
  const [asking, setAsking] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  async function decide(approve: boolean) {
    setBusy(true);
    setFailure(null);
    const result = await request<LibrarySkill>(reviewPath(one.digest), {
      method: "POST",
      body: { decision: approve ? "approve" : "reject" },
    });
    setBusy(false);
    setAsking(null);
    if (result.ok) {
      onTold({ ok: true, sentence: decidedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      <Button
        size="sm"
        className="min-h-11 sm:min-h-8"
        aria-label={`${APPROVE} ${one.name} ${one.version}`}
        onClick={() => {
          setAsking(true);
        }}
      >
        {APPROVE}
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="min-h-11 sm:min-h-8"
        aria-label={`${REJECT} ${one.name} ${one.version}`}
        onClick={() => {
          setAsking(false);
        }}
      >
        {REJECT}
      </Button>
      <ConfirmDialog
        open={asking !== null}
        question={decisionQuestion(one, asking ?? true)}
        consequence={decisionConsequence(one, asking ?? true)}
        confirmLabel={asking === false ? REJECT : APPROVE}
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={() => void decide(asking ?? true)}
        onCancel={() => {
          setAsking(null);
        }}
      />
    </>
  );
}

/** Retire or reinstate one version, confirmed (M27.15.56). */
function Retirement({ one, onTold }: { readonly one: LibrarySkill; readonly onTold: Tell }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const retired = one.retired === true;

  async function retireOrReinstate() {
    setBusy(true);
    setFailure(null);
    const result = await request<Retired>(retired ? reinstatementPath(one.digest) : retirementPath(one.digest), {
      method: "POST",
    });
    setBusy(false);
    setAsking(false);
    if (result.ok) {
      onTold({ ok: true, sentence: retiredSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      <Button
        size="sm"
        variant="outline"
        className="min-h-11 sm:min-h-8"
        onClick={() => {
          setAsking(true);
        }}
      >
        {retired ? REINSTATE : RETIRE}
      </Button>
      <ConfirmDialog
        open={asking}
        question={retired ? reinstateQuestion(one) : retireQuestion(one)}
        consequence={retired ? REINSTATE_CONSEQUENCE : RETIRE_CONSEQUENCE}
        confirmLabel={retired ? REINSTATE : RETIRE}
        cancelLabel={KEEP}
        busy={busy}
        onConfirm={() => void retireOrReinstate()}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </>
  );
}

function Version({
  one,
  newest,
  agents,
  registryIsAbsent,
  onTold,
}: {
  readonly one: LibrarySkill;
  readonly newest: boolean;
  readonly agents: readonly AgentChoice[];
  readonly registryIsAbsent: boolean;
  readonly onTold: Tell;
}) {
  const [editing, setEditing] = useState(false);
  const assignable = one.assignable && agents.length > 0;
  const acts = one.reviewable || one.editable || one.retirable === true || assignable;
  return (
    <section
      data-slot="skill-version"
      aria-label={`${one.name} ${one.version}`}
      className="flex min-w-0 flex-col gap-3 rounded-md border border-line bg-panel p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="m-0 font-mono text-[14px] font-semibold text-ink">Version {one.version}</h3>
        <ReviewPill review={one.review} />
        {one.retired === true ? <RetiredPill /> : null}
        {newest ? <span className="font-mono text-[10.5px] text-dim">newest</span> : null}
      </div>
      <p className="m-0 text-[13.5px] leading-relaxed text-body [overflow-wrap:anywhere]">{one.description}</p>
      <FactList>
        <Fact label="Added">
          {named(one.submitted_by_name, "Somebody")} {sourceWords(one)}, {dayWords(one.submitted_at)}
        </Fact>
        {one.reviewer === null ? null : (
          <Fact label="Decision">
            {decisionWords(one)}
            {one.reviewed_at === null ? "" : `, ${dayWords(one.reviewed_at)}`}
          </Fact>
        )}
        {one.retired === true ? (
          <Fact label="Retired">
            {one.retired_by ?? "Retired"}
            {one.retired_at ? `, ${dayWords(one.retired_at)}` : ""}
          </Fact>
        ) : null}
        <Fact label="Tools it uses">
          <Reach one={one} registryIsAbsent={registryIsAbsent} />
        </Fact>
      </FactList>
      {one.body === null ? null : (
        <details className="rounded-md border border-line">
          <summary className="flex min-h-11 cursor-pointer items-center px-3 text-[13px] font-medium text-ink sm:min-h-9">
            Instructions
          </summary>
          <pre className="m-0 max-h-96 overflow-auto border-t border-line bg-sunk p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-body">
            {one.body}
          </pre>
        </details>
      )}
      {one.diff === null || one.diff === undefined ? null : <Changed diff={one.diff} />}
      {editing ? (
        <EditVersionForm
          one={one}
          onTold={onTold}
          onDone={() => {
            setEditing(false);
          }}
        />
      ) : null}
      {acts && !editing ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
          {one.reviewable ? <Decide one={one} onTold={onTold} /> : null}
          {one.editable ? (
            <Button
              size="sm"
              variant="outline"
              className="min-h-11 sm:min-h-8"
              aria-label={`Edit ${one.name} ${one.version}`}
              onClick={() => {
                setEditing(true);
              }}
            >
              <Pencil aria-hidden /> Edit as a new version
            </Button>
          ) : null}
          {one.retirable === true ? <Retirement one={one} onTold={onTold} /> : null}
          {one.review === "approved" && one.retired !== true ? (
            <UnavailableAction label={TRY_OUT} text={TRY_OUT} icon={<FlaskConical aria-hidden />} reason={UNAVAILABLE.tryOut.reason} />
          ) : null}
        </div>
      ) : null}
      {assignable && !editing ? <AssignForm one={one} agents={agents} onTold={onTold} /> : null}
      <Advanced>
        <FactList>
          <Fact label="Digest">
            <span className="font-mono text-[11.5px]">{one.digest}</span>
          </Fact>
          {one.source_commit ? (
            <Fact label="Commit">
              <span className="font-mono text-[11.5px]">{one.source_commit}</span>
            </Fact>
          ) : null}
          {one.edited_from ? (
            <Fact label="Edited from">
              <span className="font-mono text-[11.5px]">{one.edited_from}</span>
            </Fact>
          ) : null}
          <Fact label="Added by">
            <span className="font-mono text-[11.5px]">{one.submitted_by}</span>
          </Fact>
          {one.reviewer === null ? null : (
            <Fact label="Decided by">
              <span className="font-mono text-[11.5px]">{one.reviewer}</span>
            </Fact>
          )}
        </FactList>
      </Advanced>
    </section>
  );
}

/** Take the skill off one agent, confirmed (M27.15.55). */
function Detach({ name, pin, agent, onTold }: { readonly name: string; readonly pin: SkillPin; readonly agent: string; readonly onTold: Tell }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  async function detach() {
    setBusy(true);
    setFailure(null);
    const result = await request<Detached>(detachPath(pin.digest), { method: "POST", body: { agent_id: pin.agent_id } });
    setBusy(false);
    setAsking(false);
    if (result.ok) {
      onTold({ ok: true, sentence: detachedSentence(result.data, agent) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      <Button
        size="sm"
        variant="outline"
        className="min-h-11 sm:min-h-8"
        aria-label={`${DETACH} ${name} from ${agent}`}
        onClick={() => {
          setAsking(true);
        }}
      >
        {DETACH}
      </Button>
      <ConfirmDialog
        open={asking}
        question={detachQuestion(name, agent)}
        consequence={detachConsequence(agent)}
        confirmLabel={DETACH}
        cancelLabel={DO_NOT_DETACH}
        busy={busy}
        onConfirm={() => void detach()}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </>
  );
}

function Agents({ detail, onTold }: { readonly detail: SkillDetail; readonly onTold: Tell }) {
  const pins = detail.pinned?.pinned_by ?? [];
  const versions = new Map(detail.versions.map((one) => [one.digest, one.version]));
  const detachable = new Set(detail.agents.map((one) => one.agent_id));
  return (
    <SectionCard
      title={AGENTS_HEADING}
      lede="The agents you can see that run it now, and the version each runs."
      footer={detail.pinned?.versions_differ === true ? <Note>{VERSIONS_DIFFER}</Note> : undefined}
    >
      {pins.length === 0 ? (
        <p className="m-0 text-[13px] text-dim">{NO_AGENTS}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
          {pins.map((pin) => {
            const agent = pin.display_name ?? "An agent";
            return (
              <li key={`${pin.agent_id}-${pin.digest}`} className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0">
                <span className="flex min-w-0 flex-col">
                  <Link to={`/agents/${encodeURIComponent(pin.agent_id)}`} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
                    {agent}
                  </Link>
                  <span className="text-[12px] text-dim">
                    {versions.has(pin.digest) ? `Version ${versions.get(pin.digest) ?? ""}` : "A version not in the library"}
                    {pin.assigned_at ? `, assigned ${dayWords(pin.assigned_at)}` : ""}
                    {pin.assigned_by ? ` by ${pin.assigned_by}` : ""}
                  </span>
                </span>
                {detachable.has(pin.agent_id) && versions.has(pin.digest) ? (
                  <span className="flex flex-wrap items-center gap-2">
                    <Detach name={detail.name} pin={pin} agent={agent} onTold={onTold} />
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}

export function SkillProfile({ detail, onTold }: { readonly detail: SkillDetail; readonly onTold: Tell }) {
  const headline = detail.versions[0];
  return (
    <div data-slot="skill-profile" className="flex min-w-0 flex-col gap-4">
      <div className="[display:grid] min-w-0 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section aria-label={VERSIONS_HEADING} className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-col gap-0.5">
            <h2 className="m-0 text-sm font-semibold text-ink">{VERSIONS_HEADING}</h2>
            <p className="m-0 text-[12.5px] text-dim">{REACH_LEDE}</p>
          </div>
          {detail.versions.length === 0 ? (
            <p className="m-0 text-[13px] text-dim">No version of this skill is in the library you can see.</p>
          ) : (
            detail.versions.map((one, index) => (
              <Version
                key={one.digest}
                one={one}
                newest={index === 0}
                agents={detail.agents}
                registryIsAbsent={detail.registryIsAbsent}
                onTold={onTold}
              />
            ))
          )}
        </section>
        <div className="flex min-w-0 flex-col gap-4">
          <Agents detail={detail} onTold={onTold} />
          {headline === undefined ? null : (
            <SectionCard title={CATEGORIES_HEADING} lede="Labels every version shares, for finding it in the library.">
              {headline.editable ? (
                <CategoriesForm one={headline} onTold={onTold} />
              ) : headline.categories.length === 0 ? (
                <p className="m-0 text-[13px] text-dim">In no category.</p>
              ) : (
                <span className="flex flex-wrap gap-1">
                  {headline.categories.map((one) => (
                    <Chip key={one}>{one}</Chip>
                  ))}
                </span>
              )}
            </SectionCard>
          )}
        </div>
      </div>
    </div>
  );
}
