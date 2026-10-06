/**
 * One agent's page on the shared kit, as `docs/screens.html` SCREEN 14 draws it: one header and its
 * figures, shared by three views in the owner's order, Dashboard, Profile and About, each at its own
 * address.
 *
 * **The addresses.** `/agents/{id}` is the Dashboard, because it opens first; `/agents/{id}/profile`
 * and `/agents/{id}/about` are the other two. A section the API's strip names keeps an address of its
 * own under `/agents/{id}/{tab}`: `automations` is the gallery and this agent's automations, and
 * `settings`, the Settings tab, is what the Profile draws, so it opens the Profile. An address naming
 * anything else opens the Dashboard silently, which is `agentWorkspaceState.openingTab`'s rule: an
 * address typed to probe for a tab lands where an address with no tab does, so it learns nothing.
 *
 * **One request for the page, and each view asks only for its own.** The workspace answer fills the
 * header and the Profile; the Dashboard asks the stats route and, for a reader of the Automations
 * tab, the installed automations; the About view asks the About route. The automation gallery is
 * asked the first time its section is opened and not again for moving between views, because this
 * component stays mounted across the views of one agent and holds the request.
 *
 * **Nothing here decides what a person may see.** Every block is drawn from what the API sent this
 * reader, and a block it sent nothing for is absent. A 404 is not explained: an agent that does not
 * exist and an agent this reader may not see are one answer, from `brain.agent_routes`.
 *
 * **What was removed from the old page, and why.** The agent's slug and the steward's principal id
 * in the header (identifiers, now in Advanced); the Dashboard and Profile pane switch beside a tab
 * strip, which put two navigations on one page; the composition diff drawn beside the capabilities
 * and again under Settings; the "Agent" heading above the agent's own name; and a strip of tab
 * purpose sentences that described the page's own structure to the person using it.
 *
 * **The header's role line (M39.1.2.1)** says what the agent is for, in its own summary, then its
 * department, its steward and the template it came from by name and version, each only when sent.
 *
 * **The sections (M39.1.2.2)** are the API's strip, in its order, each at its own address and listed
 * under Sections beside the view switch: Conversations, Automations, People, Knowledge, Memory,
 * Artifacts and Settings, whichever this reader may open and has something in it. Settings is the
 * Profile, so it is not listed twice; a section with no view on this page yet is not listed at all.
 *
 * **Moving between views keeps what a view was showing (M39.1.2.3).** This component stays mounted
 * across one agent's views and holds the Dashboard's period, so a trip to the Profile and back finds
 * the period where it was left and asks nothing again.
 *
 * **The Memory section** (`AgentMemory.tsx`) is at `/agents/{id}/memory` for a reader whose strip
 * holds it, which the API sends for every agent to a reader of the Memory tab.
 *
 * Task ids: M39.4.1.1, M39.1.2.1, M39.1.2.2, M39.1.2.3, M39.1.2.4, M39.1.2.5, M39.6.1.3, M5.7.3, M27.10.2, M27.11.6
 */

import { ChevronDown, IdCard, Info, LayoutDashboard, MessageSquarePlus, Settings } from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { AutomationGallery } from "../../components/AutomationGallery";
import { AgentAutomations } from "../../components/AgentAutomations";
import { ROSTER_ADDRESS } from "../../components/agentWorkspaceState";
import {
  DetailHeader,
  DetailPage,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  SectionCard,
  StatCard,
  UnavailableAction,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { basisWords, minorUnits } from "../../components/AgentAssembly";
import { readModelChoice } from "../agentModelPinQuery";
import { agentAutomationsApiPath } from "../agentAutomationsQuery";
import { agentWorkspaceApiPath, readAgentWorkspace } from "../agentQuery";
import { AUTOMATIONS_TAB, automationGalleryApiPath } from "../automationGalleryQuery";
import { actsFor, ACT_LABELS, type LifecycleAct } from "../agentLifecycleQuery";
import { UNAVAILABLE, WORKS_AT } from "./agentActions";
import { AgentAbout } from "./AgentAbout";
import { AgentMemory } from "./AgentMemory";
import { agentCapabilitiesApiPath, readAgentCapabilities } from "./agentCapabilitiesQuery";
import { AgentDashboard, usePeriod } from "./AgentDashboard";
import { daysSince, readHeaderFacts, readProfile, spendIsRecorded, type HeaderFacts } from "./agentDetailQuery";
import { AgentProfile, LEASH_ANCHOR } from "./AgentProfile";
import { ROSTER_HEADING, agentAddress } from "./AgentsPage";
import { useDraftStart } from "./DraftStart";
import { useLifecycleActs } from "./LifecycleActs";
import { LeashPill, StatePill } from "./pills";
import "../../styles/agent-workspace.css";

/** The three views, in the owner's order. The first is where the bare address lands. */
export const VIEWS = ["dashboard", "profile", "about"] as const;
export type AgentView = (typeof VIEWS)[number];

export const VIEW_LABELS: Readonly<Record<AgentView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

export const VIEWS_LABEL = "Agent views";
export const SECTIONS_LABEL = "Sections";
export const SETTINGS_MENU_LABEL = "Agent settings";
export const LOADING_AGENT = "Loading this agent.";
export const FIGURES_LABEL = "This agent at a glance";
export const SPEND_LABEL = "Spend, 30 days";
export const SKILLS_LABEL = "Skills";
export const DAYS_LABEL = "Days since created";
export const SPEND_NOT_RECORDED = "spend is not recorded, so the figure is left out rather than drawn as nought.";
export const AUTOMATIONS_SECTION = "Automations";

/** The Memory section's key, as the API's strip spells it. */
export const MEMORY_TAB = "memory";
export const MEMORY_SECTION = "Memory and learning";

/** A section's name as the Sections menu lists it, for the sections this page draws a view of. */
export const SECTION_LABELS: Readonly<Record<string, string>> = Object.freeze({
  [AUTOMATIONS_TAB]: AUTOMATIONS_SECTION,
  [MEMORY_TAB]: MEMORY_SECTION,
});
export const EDIT_AS_DRAFT = "Edit as a draft";

/** The settings tab's key, whose content is the Profile. */
const SETTINGS_TAB = "settings";

/**
 * The line under the agent's name: what it is for, then where it sits and where it came from.
 * Absent when nothing was sent for any part of it, never a line of separators.
 */
export function roleLine(facts: HeaderFacts, version: number | undefined): ReactNode | undefined {
  const where = [
    facts.department ?? null,
    facts.ownerName === undefined ? null : `steward ${facts.ownerName}`,
    version === undefined
      ? null
      : facts.templateName === undefined
        ? `from a template, version ${String(version)}`
        : `from ${facts.templateName}, version ${String(version)}`,
  ]
    .filter((one): one is string => one !== null)
    .join(" · ");
  if (facts.summary === undefined && where === "") {
    return undefined;
  }
  return (
    <span data-slot="role-line" className="flex flex-col gap-0.5">
      {facts.summary === undefined ? null : <span className="font-sans text-[13px] text-body">{facts.summary}</span>}
      {where === "" ? null : <span>{where}</span>}
    </span>
  );
}

/** Where a view of an agent is. The Dashboard is the bare address. */
export function viewAddress(agentId: string, view: AgentView | string): string {
  return view === VIEWS[0] ? agentAddress(agentId) : `${agentAddress(agentId)}/${encodeURIComponent(view)}`;
}

/** Which view an address opens, given the sections this reader may open. */
export function viewFor(tab: string | undefined, sections: readonly string[]): AgentView | typeof AUTOMATIONS_TAB | typeof MEMORY_TAB {
  if (tab === "profile" || tab === "about") {
    return tab;
  }
  if (tab === SETTINGS_TAB && sections.includes(SETTINGS_TAB)) {
    return "profile";
  }
  if (tab === AUTOMATIONS_TAB && sections.includes(AUTOMATIONS_TAB)) {
    return AUTOMATIONS_TAB;
  }
  if (tab === MEMORY_TAB && sections.includes(MEMORY_TAB)) {
    return MEMORY_TAB;
  }
  return "dashboard";
}

const VIEW_ICONS: Readonly<Record<AgentView, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

function SettingsMenu({
  agentId,
  state,
  onChoose,
  onEditDraft,
  busy,
}: {
  readonly agentId: string;
  readonly state: string | undefined;
  readonly onChoose: (agentId: string, act: LifecycleAct) => void;
  readonly onEditDraft: () => void;
  readonly busy: boolean;
}) {
  // The lifecycle acts are live; which of them this reader may press is the lifecycle route's to
  // say when one is chosen, and a state change is offered only for a state the API sent.
  const acts: readonly LifecycleAct[] = ["duplicate", "transfer", ...actsFor(state)];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon-sm" className="size-11 sm:size-8" aria-label={SETTINGS_MENU_LABEL}>
          <Settings aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuItem asChild>
          <Link to={WORKS_AT.instructions}>Edit instructions</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to={`${viewAddress(agentId, "profile")}#${LEASH_ANCHOR}`}>Pin a model or read the leash</Link>
        </DropdownMenuItem>
        <DropdownMenuItem disabled={busy} onSelect={onEditDraft}>
          {EDIT_AS_DRAFT}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {acts.map((act) => (
          <DropdownMenuItem
            key={act}
            disabled={busy}
            onSelect={() => {
              onChoose(agentId, act);
            }}
          >
            {ACT_LABELS[act]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SectionsMenu({ agentId, sections }: { readonly agentId: string; readonly sections: readonly { tab: string; label: string }[] }) {
  if (sections.length === 0) {
    return null;
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="min-h-11 text-body sm:min-h-8">
          {SECTIONS_LABEL} <ChevronDown aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {sections.map((one) => (
          <DropdownMenuItem key={one.tab} asChild>
            <Link to={viewAddress(agentId, one.tab)}>{one.label}</Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * One agent's answer. Keyed on the agent by the page, so another agent's answer never shows while
 * this one's is in flight; kept across this agent's views, so the gallery is asked once.
 */
function AgentAnswer({ agentId, tab }: { readonly agentId: string; readonly tab: string | undefined }) {
  // Asked again under a new version after a lifecycle act, so the header shows what the API now holds.
  const [agentVersion, setAgentVersion] = useState(0);
  const onMoved = useCallback(() => {
    setAgentVersion((count) => count + 1);
  }, []);
  const lifecycle = useLifecycleActs(onMoved, agentAddress);
  const drafting = useDraftStart();
  const [period, setPeriod] = usePeriod();
  const answer = useResource<unknown>(agentWorkspaceApiPath(agentId), agentVersion);
  const workspace = useMemo(() => readAgentWorkspace(answer.data), [answer.data]);
  const facts = useMemo(() => readHeaderFacts(answer.data), [answer.data]);
  const profile = useMemo(() => readProfile(answer.data), [answer.data]);
  const choice = useMemo(() => readModelChoice(answer.data), [answer.data]);
  const recorded = spendIsRecorded(answer.data);

  const sections = workspace?.tabs.map((one) => one.tab) ?? [];
  const view = viewFor(tab, sections);
  const readsAutomations = sections.includes(AUTOMATIONS_TAB);

  // The gallery and the installed automations: asked when the section is first opened (or, for
  // the installed list, when the Dashboard shows them), and again under a new version after an
  // install, a start or a stop, so nothing on the page is rebuilt.
  const [galleryShown, setGalleryShown] = useState(false);
  const [version, setVersion] = useState(0);
  const wantsAutomations = readsAutomations && (view === AUTOMATIONS_TAB || view === "dashboard");
  const gallery = useResource<unknown>(galleryShown ? automationGalleryApiPath(agentId) : null, version);
  const automations = useResource<unknown>(wantsAutomations ? agentAutomationsApiPath(agentId) : null, version);
  const onShown = useCallback(() => {
    setGalleryShown(true);
  }, []);
  // The Profile's capability detail: asked when the Profile is shown, and again under a new
  // version after a skill is attached or taken off there.
  const [detailVersion, setDetailVersion] = useState(0);
  const detailAnswer = useResource<unknown>(view === "profile" ? agentCapabilitiesApiPath(agentId) : null, detailVersion);
  const details = useMemo(() => (detailAnswer.data === null ? null : readAgentCapabilities(detailAnswer.data)), [detailAnswer.data]);
  const onDetailsChanged = useCallback(() => {
    setDetailVersion((count) => count + 1);
  }, []);
  const onChanged = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy) {
    return <LoadingState label={LOADING_AGENT} />;
  }
  if (workspace === null) {
    return null;
  }
  const { agent } = workspace;
  const editDraft = () => {
    drafting.begin({ kind: "agent", agentId, name: agent.displayName });
  };
  const headingId = `agent-${agent.agentId}`;
  const figures = workspace.figures;
  const views: DetailView[] = VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: VIEW_LABELS[one], to: viewAddress(agentId, one), icon: <Icon aria-hidden /> };
  });
  const menuSections = workspace.tabs
    .filter((one) => SECTION_LABELS[one.tab] !== undefined)
    .map((one) => ({ tab: one.tab, label: SECTION_LABELS[one.tab] ?? one.label }));
  const subline = roleLine(facts, agent.lineage?.version);

  const header = (
    <DetailHeader
      name={agent.displayName}
      headingId={headingId}
      pills={
        <>
          {facts.state === undefined ? null : <StatePill state={facts.state} />}
          {facts.leashUpTo === undefined ? null : <LeashPill rung={facts.leashUpTo} upTo />}
        </>
      }
      subline={subline}
      actions={
        <>
          {profile === null ? null : (
            <SettingsMenu
              agentId={agentId}
              state={facts.state}
              onChoose={lifecycle.choose}
              onEditDraft={editDraft}
              busy={lifecycle.busy || drafting.busy}
            />
          )}
          <UnavailableAction
            text="Add to a chat group"
            label="Add to a chat group"
            icon={<MessageSquarePlus aria-hidden />}
            reason={UNAVAILABLE.chatGroup.reason}
          />
        </>
      }
      figures={
        <KpiStrip label={FIGURES_LABEL} count={workspace.skills.length > 0 ? 3 : 2}>
          <StatCard
            label={SPEND_LABEL}
            value={recorded && figures !== undefined ? minorUnits(figures.spendMinor) : undefined}
            sub={figures === undefined ? undefined : basisWords(figures.basis)}
            link={
              recorded ? (
                <Link to={WORKS_AT.usage} aria-label="Open usage and cost" className="text-[12px] font-normal text-acc-text underline-offset-4 hover:underline">
                  Usage
                </Link>
              ) : undefined
            }
          />
          {workspace.skills.length > 0 ? (
            <StatCard label={SKILLS_LABEL} value={String(workspace.skills.length)} sub="assigned, each a pinned version" />
          ) : null}
          <StatCard
            label={DAYS_LABEL}
            value={facts.createdAt === undefined ? undefined : String(daysSince(facts.createdAt))}
            sub={facts.createdAt === undefined ? undefined : `created ${new Date(facts.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}`}
          />
        </KpiStrip>
      }
      footnote={recorded ? undefined : <Note kind="not-yet">{SPEND_NOT_RECORDED}</Note>}
    />
  );

  return (
    <DetailPage
      crumbs={[{ label: ROSTER_HEADING, to: ROSTER_ADDRESS }, { label: agent.displayName }]}
      header={header}
      switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view === AUTOMATIONS_TAB || view === MEMORY_TAB ? undefined : view} />}
      beside={<SectionsMenu agentId={agentId} sections={menuSections} />}
    >
      {lifecycle.notice}
      {lifecycle.dialog}
      {drafting.notice}
      {drafting.dialog}
      {view === "dashboard" ? (
        <AgentDashboard
          agentId={agentId}
          period={period}
          onPeriod={setPeriod}
          automationsAddress={readsAutomations ? viewAddress(agentId, AUTOMATIONS_TAB) : undefined}
          automations={readsAutomations ? automations : undefined}
          onAutomationsChanged={onChanged}
        />
      ) : null}
      {view === "profile" ? (
        <AgentProfile
          agent={agent}
          facts={facts}
          profile={profile}
          choice={choice}
          connectors={workspace.connectors}
          skills={workspace.skills}
          channels={workspace.channels}
          composition={workspace.composition}
          divergent={workspace.divergent}
          details={details}
          onDetailsChanged={onDetailsChanged}
          onTransfer={() => {
            lifecycle.choose(agentId, "transfer");
          }}
          onEditDraft={editDraft}
        />
      ) : null}
      {view === "about" ? <AgentAbout agentId={agentId} profileAddress={viewAddress(agentId, "profile")} /> : null}
      {view === MEMORY_TAB ? <AgentMemory agentId={agentId} /> : null}
      {view === AUTOMATIONS_TAB ? (
        <SectionCard title={AUTOMATIONS_SECTION} lede="What this agent runs on a schedule, and what can be installed for it.">
          <div className="flex min-w-0 flex-col gap-4">
            <AgentAutomations agentId={agentId} automations={automations} onChanged={onChanged} />
            <AutomationGallery agentId={agentId} gallery={gallery} onShown={onShown} onInstalled={onChanged} />
          </div>
        </SectionCard>
      ) : null}
    </DetailPage>
  );
}

export function AgentDetailPage({ agentId, tab }: { readonly agentId: string; readonly tab: string | undefined }) {
  return (
    <div data-slot="agent-page" className="min-w-0">
      <AgentAnswer key={agentId} agentId={agentId} tab={tab} />
    </div>
  );
}
