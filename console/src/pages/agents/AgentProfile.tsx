/**
 * The Profile view of one agent: what it is built from, who can find it, the most it may reach, how
 * much a person is involved before it acts, and how it differs from its template.
 *
 * **It folds in what the old workspace spread across a tab strip and two panes.** Configuration,
 * skills, tools and reach, the leash and the template's versions were a Settings tab, a Profile
 * pane and a Dashboard pane with the composition repeated beside the capabilities; SCREEN 14 puts
 * them on one page in cards, and each card is drawn only when the API sent this reader what it
 * holds. A card the reader was sent nothing for is absent, not empty with a heading over it, which
 * would be a count of hidden things in words.
 *
 * **Every control is live or says why it is not.** Pinning a model, assigning a skill and handing the
 * agent on have routes and work (the skill on the Skills page, where an approved skill is chosen, and
 * the hand-over through the page's confirmed lifecycle act); adding a source and changing permissions
 * are changes to the agent's manifest, so each starts a draft of the agent through the page's
 * confirmed Edit as a draft. Choosing channels, changing who can find it, previewing as a person,
 * changing a rung and browser use have no route and are `UnavailableAction`s with `agentActions.ts`'
 * sentences. Computer use is a sentence, because the product has nothing behind a switch.
 *
 * **Identifiers are in the Advanced section.** The agent's slug, the steward's and builder's
 * principal ids and the template's id are how the system names them; the cards show names and
 * words, and `kit/parts.tsx`' `Advanced` holds the rest for a support request.
 *
 * Task ids: M27.10.2, M5.7.3, M27.11.6
 */

import { Brain, Globe, MonitorX, Plug, Radio, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { AgentModelPin } from "../../components/AgentModelPin";
import { CompositionDiff } from "../../components/CompositionDiff";
import type { AgentIdentity, DiffRow } from "../../components/agentWorkspaceState";
import {
  Advanced,
  Chip,
  Fact,
  FactList,
  Note,
  NotOffered,
  SectionCard,
  UnavailableAction,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Switch } from "../../components/ui/switch";
import type { ModelChoice } from "../agentModelPinQuery";
import { ConnectorsDetail, KnowledgeCard, PreviewForm, SkillsDetail } from "./AgentCapabilities";
import type { AgentCapabilities } from "./agentCapabilitiesQuery";
import type { ChannelOffer, ConnectorStrip, SkillPin } from "../agentQuery";
import { LEVEL_WORDS, RUNGS_EXPLAINED, TIER_WORDS, UNAVAILABLE, WORKS_AT } from "./agentActions";
import { leashRowId, type HeaderFacts, type ProfileShown } from "./agentDetailQuery";
import { LeashPill } from "./pills";

export const CAPABILITIES_HEADING = "Capabilities";
export const PERMISSIONS_HEADING = "Permissions";
export const AVAILABILITY_HEADING = "Availability";
export const MODEL_HEADING = "Model and autonomy";
export const TEMPLATE_HEADING = "Template and local changes";
export const LEARNING_HEADING = "Learning from conversations";
export const BROWSER_HEADING = "Browser use";
export const COMPUTER_HEADING = "Computer use";

/** A source and a permission are changed through a draft of the agent. */
export const ADD_A_SOURCE = "Add a source to this agent, through a draft";
export const CHANGE_PERMISSIONS = "Change permissions";
export const CHANGE_THROUGH_A_DRAFT =
  "Starts a draft of this agent. A wider change waits for a second person to approve it, and starts at Shadow.";

/** The id the leash list carries, which the About view links to. */
export const LEASH_ANCHOR = "leash";

function CapabilityRow({
  icon,
  label,
  add,
  children,
  note,
}: {
  readonly icon: ReactNode;
  readonly label: string;
  readonly add?: ReactNode | undefined;
  readonly children: ReactNode;
  readonly note?: ReactNode | undefined;
}) {
  return (
    <div className="[display:grid] grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 border-b border-line py-3 first:pt-0 last:border-b-0 last:pb-0 sm:grid-cols-[8.5rem_minmax(0,1fr)_auto]">
      <div className="col-start-1 flex items-center gap-2 text-[13px] font-medium text-ink sm:self-start sm:pt-1 [&>svg]:size-4 [&>svg]:text-dim">
        {icon}
        {label}
      </div>
      <div className="col-start-2 row-start-1 flex items-start justify-end sm:col-start-3">{add}</div>
      <div className="col-span-2 flex min-w-0 flex-col gap-2 sm:col-span-1 sm:col-start-2 sm:row-start-1">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">{children}</div>
        {note}
      </div>
    </div>
  );
}

function Capabilities({
  agentId,
  connectors,
  skills,
  channels,
  details,
  onDetailsChanged,
  onEditDraft,
}: {
  readonly agentId: string;
  readonly connectors: ConnectorStrip;
  readonly skills: readonly SkillPin[];
  readonly channels: readonly ChannelOffer[];
  readonly details: AgentCapabilities | null;
  readonly onDetailsChanged: () => void;
  readonly onEditDraft?: (() => void) | undefined;
}) {
  const detailed = details !== null && (details.connectors.length > 0 || details.skills.length > 0 || details.offers.length > 0);
  if (!detailed && connectors.shown.length === 0 && skills.length === 0 && channels.length === 0) {
    return null;
  }
  return (
    <SectionCard title={CAPABILITIES_HEADING} lede="What this agent is built from. Each is a reviewed item it refers to, never a copy.">
      {details !== null && details.connectors.length > 0 ? (
        <CapabilityRow
          icon={<Plug aria-hidden />}
          label="Connectors"
          add={
            onEditDraft === undefined ? null : (
              <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={ADD_A_SOURCE} title={ADD_A_SOURCE} onClick={onEditDraft}>
                <span aria-hidden>+</span>
              </Button>
            )
          }
        >
          <ConnectorsDetail connectors={details.connectors} />
        </CapabilityRow>
      ) : connectors.shown.length === 0 ? null : (
        <CapabilityRow
          icon={<Plug aria-hidden />}
          label="Connectors"
          add={
            onEditDraft === undefined ? null : (
              <Button
                variant="ghost"
                size="icon-sm"
                className="size-11 sm:size-8"
                aria-label={ADD_A_SOURCE}
                title={ADD_A_SOURCE}
                onClick={onEditDraft}
              >
                <span aria-hidden>+</span>
              </Button>
            )
          }
          note={
            <Note>
              Attached means the agent is set up to use the source. Requested means its setup asks for it and nothing links it yet.
            </Note>
          }
        >
          {connectors.shown.map((one) =>
            // The word says it and the dashed edge repeats it, so the difference is never colour
            // alone; `tests/status-primitives.test.tsx` holds that no tone is computed from data.
            one.presence === "attached" ? (
              <Chip key={one.source} mono>
                {one.source}
              </Chip>
            ) : (
              <Chip key={one.source} mono tone="requested">
                {`${one.source} · ${one.presence}`}
              </Chip>
            ),
          )}
          {connectors.overflow > 0 ? <Chip tone="requested">{`${String(connectors.overflow)} more on this agent`}</Chip> : null}
        </CapabilityRow>
      )}
      {details !== null && (details.skills.length > 0 || details.offers.length > 0) ? (
        <CapabilityRow icon={<Sparkles aria-hidden />} label="Skills">
          <SkillsDetail
            agentId={agentId}
            skills={details.skills}
            offers={details.offers}
            editable={details.skillsEditable}
            unused={details.unusedSkills}
            basis={details.usageBasis}
            onChanged={onDetailsChanged}
          />
        </CapabilityRow>
      ) : skills.length === 0 ? null : (
        <CapabilityRow
          icon={<Sparkles aria-hidden />}
          label="Skills"
          add={
            <Link to={WORKS_AT.skills} className="inline-flex min-h-11 items-center text-[12.5px] text-acc-text underline-offset-4 hover:underline sm:min-h-8">
              Assign a skill
            </Link>
          }
          note={<Note kind="not-yet">using skills when the agent answers. An assignment is saved and changes no answer today.</Note>}
        >
          {skills.map((one) => (
            <Chip key={one.digest} mono tone="brand">
              {one.name}
            </Chip>
          ))}
        </CapabilityRow>
      )}
      {channels.length === 0 ? null : (
        <CapabilityRow
          icon={<Radio aria-hidden />}
          label="Channels"
          add={<UnavailableAction size="icon-sm" icon={<span aria-hidden>+</span>} label="Choose where this agent answers" reason={UNAVAILABLE.chatGroup.reason} />}
          note={<Note>The chats and email that could carry this agent's answers to you, not the ones switched on.</Note>}
        >
          {channels.map((one) => (
            <Chip key={one.channel} mono>
              {one.channel} <span className="text-dim">as {one.profile}</span>
            </Chip>
          ))}
        </CapabilityRow>
      )}
    </SectionCard>
  );
}

function Permissions({
  agentId,
  profile,
  onEditDraft,
}: {
  readonly agentId: string;
  readonly profile: ProfileShown;
  readonly onEditDraft?: (() => void) | undefined;
}) {
  const { ceiling } = profile;
  if (ceiling === undefined) {
    return null;
  }
  return (
    <SectionCard
      title={PERMISSIONS_HEADING}
      lede="The most this agent may ever reach. Each time it works it holds what the person it works for holds, narrowed by this. It gives nobody extra access."
      action={<ShieldCheck aria-hidden className="size-4 text-dim" />}
      footer={
        <div className="flex flex-col gap-3">
          {onEditDraft === undefined ? null : (
            <div>
              <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" title={CHANGE_THROUGH_A_DRAFT} onClick={onEditDraft}>
                {CHANGE_PERMISSIONS}
              </Button>
            </div>
          )}
          <PreviewForm agentId={agentId} />
        </div>
      }
    >
      <FactList>
        <Fact label="Records">{ceiling.rows}</Fact>
        <Fact label="May read">
          {ceiling.readsLocked ? (
            <span className="text-dim">Shown to people who may read the capability list.</span>
          ) : ceiling.reads.length === 0 ? (
            <span className="text-dim">Nothing beyond the records above.</span>
          ) : (
            <ul className="m-0 flex list-disc flex-col gap-0.5 pl-4">
              {ceiling.reads.map((one) => (
                <li key={one}>{one}</li>
              ))}
            </ul>
          )}
        </Fact>
        <Fact label="Actions">{ceiling.tools}</Fact>
        <Fact label="At most">{ceiling.largestEffect}</Fact>
      </FactList>
    </SectionCard>
  );
}

function Availability({
  facts,
  profile,
  details,
  onTransfer,
}: {
  readonly facts: HeaderFacts;
  readonly profile: ProfileShown | null;
  readonly details: AgentCapabilities | null;
  readonly onTransfer?: (() => void) | undefined;
}) {
  const availability = details?.availability;
  return (
    <SectionCard title={AVAILABILITY_HEADING} lede="Who can find and start this agent. This never gives anybody access to more information.">
      <FactList>
        {profile?.audienceLevel === undefined ? null : (
          <Fact label="Level">
            <span className="flex flex-wrap items-center gap-2">
              <Chip>{LEVEL_WORDS[profile.audienceLevel] ?? profile.audienceLevel}</Chip>
              <UnavailableAction size="xs" text="Change" label="Change who can find this agent" reason={UNAVAILABLE.level.reason} />
            </span>
          </Fact>
        )}
        <Fact label="Steward">
          <span className="flex flex-wrap items-center gap-2">
            {facts.ownerName === undefined ? <span className="text-dim">Not named in the directory</span> : <Chip>{facts.ownerName}</Chip>}
            {profile === null || onTransfer === undefined ? null : (
              <Button variant="outline" size="xs" onClick={onTransfer}>
                Transfer
              </Button>
            )}
          </span>
        </Fact>
        {availability?.department === undefined ? null : (
          <Fact label="Department">
            <Chip>{availability.department}</Chip>
          </Fact>
        )}
        {availability === undefined ? null : (
          <Fact label="You">
            {availability.readerIsIncluded ? "You can find and start it." : "You are not among the people who can find it."}
          </Fact>
        )}
        <Fact label="People">
          <NotOffered>
            Not a list of people. Who can find it is set by the level: Personal is the steward only, Department is everyone in it, Company
            is everyone.
          </NotOffered>
        </Fact>
      </FactList>
    </SectionCard>
  );
}

function ModelAndAutonomy({
  agentId,
  profile,
  choice,
}: {
  readonly agentId: string;
  readonly profile: ProfileShown;
  readonly choice: ModelChoice | null;
}) {
  // A link from the About view lands here with a leash row's id in the address. The router does
  // not scroll to a hash, so the row is scrolled to and marked from the address.
  const { hash } = useLocation();
  const wanted = hash.slice(1);
  useEffect(() => {
    if (wanted !== "") {
      globalThis.document.getElementById(wanted)?.scrollIntoView?.({ block: "center" });
    }
  }, [wanted]);
  return (
    <SectionCard title={MODEL_HEADING} lede="Which size of model it asks for, and how much a person is involved before each action.">
      <FactList>
        {profile.tier === undefined ? null : (
          <Fact label="Model size">
            <span className="flex flex-col gap-2">
              <span className="flex flex-wrap items-center gap-1.5">
                <Chip tone="brand">{TIER_WORDS[profile.tier] ?? profile.tier}</Chip>
              </span>
              <Note kind="not-yet">the size is saved and not yet used when it answers.</Note>
            </span>
          </Fact>
        )}
      </FactList>
      {choice === null ? null : (
        <div className="mt-3">
          <AgentModelPin agentId={agentId} choice={choice} />
        </div>
      )}
      <div id={LEASH_ANCHOR} className="mt-3 scroll-mt-24">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[13px] font-medium text-ink">Approval setting, by action</span>
          <UnavailableAction size="xs" text="Change" label="Change an approval setting" reason={UNAVAILABLE.leash.reason} />
        </div>
        {profile.leash.length === 0 ? (
          <Note>It takes no action, so there is nothing for a person to approve.</Note>
        ) : (
          <ul className="m-0 flex list-none flex-col rounded-md border border-line p-0">
            {profile.leash.map((one) => {
              const tool = profile.tools.find((candidate) => candidate.name === one.target);
              const marked = wanted === leashRowId(one.target);
              return (
                <li
                  key={one.target}
                  id={leashRowId(one.target)}
                  aria-current={marked ? "location" : undefined}
                  className={
                    marked
                      ? "[display:grid] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line bg-acc-wash px-3 py-2 last:border-b-0"
                      : "[display:grid] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line px-3 py-2 last:border-b-0"
                  }
                >
                  <span className="min-w-0 text-[13px] text-ink [overflow-wrap:anywhere]">{tool?.description ?? one.target}</span>
                  <LeashPill rung={one.rung} />
                  {one.configured ? null : <span className="col-span-2 text-[11.5px] text-dim">No setting, so it only practises.</span>}
                </li>
              );
            })}
          </ul>
        )}
        <div className="mt-2">
          <Note>{RUNGS_EXPLAINED}</Note>
        </div>
      </div>
    </SectionCard>
  );
}

function Learning() {
  const tiers: readonly (readonly [string, string, string])[] = [
    ["1", "Within a conversation", "Stays inside the conversation it came from."],
    ["2", "Automatic", "Changes how it answers, never what anybody may see."],
    ["3", "After agreement", "Suggested first, applied once separate conversations agree."],
    ["4", "Needs a person", "Would change who may see what. A person decides."],
  ];
  return (
    <SectionCard
      title={LEARNING_HEADING}
      lede="What it may learn from answered questions, ordered by how far a change would reach."
      action={<Brain aria-hidden className="size-4 text-dim" />}
      footer={
        <>
          <Note>There is deliberately no single on and off switch, because one switch would let anything be learnt unchecked.</Note>
          <Link to={WORKS_AT.learning} className="w-fit text-[12px] text-acc-text underline-offset-4 hover:underline">
            Open the learning review
          </Link>
        </>
      }
    >
      <ol className="m-0 flex list-none flex-col p-0">
        {tiers.map(([n, name, words]) => (
          <li key={n} className="[display:grid] grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2 border-b border-line py-2 text-[13px] last:border-b-0 sm:grid-cols-[1.5rem_9rem_minmax(0,1fr)]">
            <span className="font-mono text-[11px] text-dim">{n}</span>
            <span className="font-medium text-ink">{name}</span>
            <span className="col-start-2 text-body sm:col-start-3">{words}</span>
          </li>
        ))}
      </ol>
    </SectionCard>
  );
}

function BrowserUse() {
  return (
    <SectionCard title={BROWSER_HEADING} lede="Using a web browser for a task, in a sealed browser thrown away afterwards." action={<Globe aria-hidden className="size-4 text-dim" />}>
      <div className="flex items-center justify-between gap-3 rounded-md border border-dashed border-line px-3 py-2.5">
        <label htmlFor="agent-browser-use" className="text-[13px] text-dim">
          Let this agent use a browser
        </label>
        <Switch id="agent-browser-use" disabled aria-describedby="agent-browser-use-why" />
      </div>
      <div id="agent-browser-use-why" className="mt-2">
        <Note kind="not-yet">{UNAVAILABLE.browser.reason.replace(/^Not available yet: /, "")}</Note>
      </div>
    </SectionCard>
  );
}

function ComputerUse() {
  return (
    <SectionCard title={COMPUTER_HEADING} action={<MonitorX aria-hidden className="size-4 text-dim" />}>
      <NotOffered>
        Not offered. Nothing in the product controls a computer's screen, keyboard or mouse, so there is no switch. An agent acts only
        through actions the product checks first.
      </NotOffered>
    </SectionCard>
  );
}

export function AgentProfile({
  agent,
  facts,
  profile,
  choice,
  connectors,
  skills,
  channels,
  composition,
  divergent,
  details,
  onDetailsChanged,
  onTransfer,
  onEditDraft,
}: {
  readonly agent: AgentIdentity;
  readonly facts: HeaderFacts;
  readonly profile: ProfileShown | null;
  readonly choice: ModelChoice | null;
  readonly connectors: ConnectorStrip;
  readonly skills: readonly SkillPin[];
  readonly channels: readonly ChannelOffer[];
  readonly composition: readonly DiffRow[];
  readonly divergent: readonly string[];
  /** The capability detail `agent_capability_routes` sent, or null while it is on its way. */
  readonly details: AgentCapabilities | null;
  /** Asks the detail again after a skill is attached or taken off. */
  readonly onDetailsChanged: () => void;
  /** Opens the page's confirmed hand-over. Absent where the page offers none. */
  readonly onTransfer?: (() => void) | undefined;
  /** Opens the page's confirmed Edit as a draft. Absent where the page offers none. */
  readonly onEditDraft?: (() => void) | undefined;
}) {
  return (
    <div data-slot="agent-profile" className="flex min-w-0 flex-col gap-4">
      <div className="[display:grid] min-w-0 gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Capabilities
            agentId={agent.agentId}
            connectors={connectors}
            skills={skills}
            channels={channels}
            details={details}
            onDetailsChanged={onDetailsChanged}
            onEditDraft={onEditDraft}
          />
          {details?.knowledge === undefined ? null : <KnowledgeCard knowledge={details.knowledge} onWiden={onEditDraft} />}
          <Availability facts={facts} profile={profile} details={details} onTransfer={onTransfer} />
          <Learning />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          {profile === null ? null : <Permissions agentId={agent.agentId} profile={profile} onEditDraft={onEditDraft} />}
          {profile === null ? null : <ModelAndAutonomy agentId={agent.agentId} profile={profile} choice={choice} />}
        </div>
      </div>
      {composition.length === 0 ? null : (
        <SectionCard
          title={TEMPLATE_HEADING}
          lede={
            agent.lineage === undefined
              ? "This agent beside the template it came from."
              : `Installed from version ${String(agent.lineage.version)} of its template, beside what this install changed.`
          }
          footer={
            divergent.length === 0 ? undefined : <Note>{`Changed here from the template: ${divergent.join(", ")}.`}</Note>
          }
        >
          <CompositionDiff rows={composition} />
        </SectionCard>
      )}
      <div className="[display:grid] min-w-0 items-start gap-4 lg:grid-cols-2">
        <BrowserUse />
        <ComputerUse />
      </div>
      <Advanced>
        <FactList>
          <Fact label="Agent id">
            <code>{agent.agentId}</code>
          </Fact>
          {agent.ownerId === undefined ? null : (
            <Fact label="Steward id">
              <code>{agent.ownerId}</code>
            </Fact>
          )}
          {agent.createdBy === undefined ? null : (
            <Fact label="Built by">
              <code>{agent.createdBy}</code>
            </Fact>
          )}
          {agent.lineage === undefined ? null : (
            <Fact label="Template">
              <code>{`${agent.lineage.templateId} v${String(agent.lineage.version)}`}</code>
            </Fact>
          )}
        </FactList>
      </Advanced>
    </div>
  );
}
