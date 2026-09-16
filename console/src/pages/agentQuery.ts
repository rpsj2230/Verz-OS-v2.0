/**
 * What the agent page asks the API for, and how an answer becomes the shapes the workspace
 * draws.
 *
 * **`brain.agent_routes` answers this address, and the reader is checked against its declared
 * schema.** Until 2026-09-14 nothing did, and every agent rendered the API's 404 sentence. The
 * route answers an agent outside the reader's audience with exactly the 404 and body a slug
 * nothing holds gets, so the page still cannot tell the two apart and still renders the one
 * sentence for both. `tests/agent-page.test.tsx` reads every wire name below off the route's
 * declared response schema, and pins that `set_by` is not declared: the route withholds it.
 *
 * **Every wire name but three is a field name the Python side already has.** `agent_id` and
 * `display_name` are `AgentRecord`'s, `owner_id` is `AgentAudience`'s, `summary` is
 * `ManifestIdentity`'s, `template_id` and `template_version` are `TemplateInstance`'s, `tab`
 * and `purpose` are `WorkspaceTab`'s, and `source` and `set_by` are `FieldOwner`'s; the test
 * reads each back out of its model. The three this console proposes, because no model holds
 * them, are a tab's `label` and the `template` and `instance` sides of a diff row, which are
 * spelled as the two `FieldSource` members they stand for. That is the position
 * `console/README.md` records for `readGraph`, and it has the same quiet failure: a route
 * written with other names renders an agent with less on the screen, never with more.
 *
 * **A withheld field and an absent one are one absence by the time they leave this file.** A
 * key that is missing, null, empty or of the wrong type is not carried, so no renderer has a
 * value to branch on. Two of the rules are about pairs rather than fields, and they are the two
 * a tolerant reader breaks: a lineage is a template and a version or it is neither, and a diff
 * row is both sides or it is not a row. See
 * `AN_ABSENT_FIELD_AND_A_WITHHELD_ONE_ARE_ONE_ABSENCE`,
 * `A_LINEAGE_IS_A_TEMPLATE_AND_A_VERSION_OR_IT_IS_NEITHER` and
 * `A_DIFF_ROW_CARRIES_BOTH_SIDES_OR_IT_IS_NOT_A_ROW` in `components/agentWorkspaceState.ts`.
 *
 * **Nothing here decides what a person may see.** It drops what is malformed and carries what
 * arrived. The strip is `brain.console.workspace.tab_strip`'s answer and is not filtered again,
 * and a diff row is never dropped for anything it says, only for not saying both sides.
 *
 * Rejected: the tab in the request. Which tab is open is decided in the browser, out of the
 * strip the API answered, and that strip is the same whichever tab the address names; a
 * request carrying the tab would be a second question with the same answer, and the first
 * change anybody made to the route would be to let the two differ.
 *
 * Task ids: M39.1.2.1, M39.1.1.5
 */

import type {
  AgentIdentity,
  DiffRow,
  WorkspaceTabView,
} from "../components/agentWorkspaceState";

/** Where one agent's workspace is asked for, under the API base. */
export function agentWorkspaceApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/workspace`;
}

/**
 * One skill this agent is pinned to, as `brain.agent_routes.SkillView` sends one.
 *
 * A name and a digest and no review word. The route says why: the approved library has no
 * table on this installation, so a chip reading approved would be about bytes nobody here has
 * read. A console that supplied one would be inventing the very state
 * `brain.console.agent_tabs.Review` exists to keep honest.
 */
export interface SkillPin {
  readonly name: string;
  /** The digest the pin is over, which is what a run resolves rather than the version. */
  readonly digest: string;
}

/**
 * One connector this agent names, as this reader may see it.
 *
 * `presence` is rendered as it arrived, which is `src/ui/Status.tsx`'s rule about a state
 * word: `brain.console.workspace_capabilities.Presence` has two members, the console acts on
 * neither, and a word that is neither renders as itself rather than as a guess.
 */
export interface ConnectorPresence {
  readonly source: string;
  readonly presence: string;
}

/**
 * The connector row and the count beside it.
 *
 * `overflow` is the one number this console draws about a list, and it is legitimate for the
 * reason `AN_OVERFLOW_COUNTS_WHAT_IS_OFF_THE_ROW_AND_NEVER_WHAT_IS_OUT_OF_REACH` gives on the
 * Python side: it is computed from the rows this reader may see, so it counts what is off the
 * end of the row and never what is out of reach. It is carried only as a whole number from
 * one, so a body sending a string or a negative draws nothing.
 */
export interface ConnectorStrip {
  readonly shown: readonly ConnectorPresence[];
  readonly overflow: number;
}

/** One surface a run of this agent could be carried on, and how it would be laid out. */
export interface ChannelOffer {
  readonly channel: string;
  /** `brain.console.agent_tabs.RenderProfile`, derived by the adapter's own capabilities. */
  readonly profile: string;
}

/**
 * The agent's figures, and whose they are.
 *
 * `basis` is required and is not decoration: a figure with no label is read as the agent's
 * total, so a reader shown their own spend would read it as everybody's. A body with no basis
 * carries no figures at all here, which is the direction this has to fail in.
 */
export interface AgentFigures {
  readonly basis: string;
  readonly range: string;
  readonly spendMinor: number;
  readonly runs: number;
}

/** One agent's workspace, as this console holds it. No field here is a count of what was
 * withheld, and the one number is an overflow over rows this reader was shown. */
export interface AgentWorkspaceAnswer {
  readonly agent: AgentIdentity;
  /** The strip, in the order the API answered it. */
  readonly tabs: readonly WorkspaceTabView[];
  /** The composition beside its template, path by path, in the order the API answered it. */
  readonly composition: readonly DiffRow[];
  /** The composition parts this install has edited that its template supplies. */
  readonly divergent: readonly string[];
  readonly skills: readonly SkillPin[];
  readonly connectors: ConnectorStrip;
  readonly channels: readonly ChannelOffer[];
  /** Absent when the API sent no figures, which is not the same as figures of nought. */
  readonly figures?: AgentFigures;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said` or `pinnedVersion` below, which narrow everything this widens.
  return value as Fields;
}

/**
 * A string with something in it, or nothing. Never a default.
 *
 * The empty string is nothing rather than a value, on every field including the two sides of a
 * diff row: those are JSON text, and JSON spells every value it has, the empty string among
 * them, with at least one character. An empty side is a side that was not sent.
 */
function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/** A published version: a whole number from one, as `TemplateInstance.template_version` is. */
function pinnedVersion(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 1 ? value : undefined;
}

/**
 * The agent a header is about, or `null` when the body names no agent.
 *
 * The id and the name are required, because an agent that reached this page is one the
 * reader's audience covers and both are already theirs. The other three are separate answers
 * and each is carried only when it was given.
 *
 * **The owner is `owner_id` and never `created_by`.** `brain.agents.model` keeps the current
 * steward and the original builder apart on purpose, and a reader that fell back from one to
 * the other would put the name of somebody who handed the agent on a year ago where the
 * person who answers for it goes, on exactly the agents whose steward is withheld.
 */
export function readAgent(payload: unknown): AgentIdentity | null {
  const fields = fieldsOf(payload);
  const agentId = said(fields?.["agent_id"]);
  const displayName = said(fields?.["display_name"]);
  if (fields === null || agentId === undefined || displayName === undefined) {
    return null;
  }
  const roleLine = said(fields["summary"]);
  const ownerId = said(fields["owner_id"]);
  const createdBy = said(fields["created_by"]);
  const templateId = said(fields["template_id"]);
  const version = pinnedVersion(fields["template_version"]);
  return {
    agentId,
    displayName,
    ...(roleLine === undefined ? {} : { roleLine }),
    ...(ownerId === undefined ? {} : { ownerId }),
    // Carried under its own name and never folded into the owner. The route sends it to a
    // reader of the Settings tab and to nobody else, so an absent key here is a reader who
    // was not told rather than an agent nobody built.
    ...(createdBy === undefined ? {} : { createdBy }),
    // Both or neither. Half a lineage is the count of hidden things spelled out in words.
    ...(templateId === undefined || version === undefined
      ? {}
      : { lineage: { templateId, version } }),
  };
}

/**
 * The strip, in the order it arrived, keeping the tabs that say what they are.
 *
 * A tab with no key, no label or no purpose is dropped rather than given one, and so is a
 * second tab under a key already read: two buttons sharing a key share an id, and the arrow
 * keys would move to whichever of them was registered last. Nothing else is dropped, and
 * nothing is reordered.
 */
export function readTabs(payload: unknown): WorkspaceTabView[] {
  if (!Array.isArray(payload)) {
    return [];
  }
  const seen = new Set<string>();
  const tabs: WorkspaceTabView[] = [];
  for (const entry of payload as readonly unknown[]) {
    const fields = fieldsOf(entry);
    const tab = said(fields?.["tab"]);
    const label = said(fields?.["label"]);
    const purpose = said(fields?.["purpose"]);
    if (tab === undefined || label === undefined || purpose === undefined || seen.has(tab)) {
      continue;
    }
    seen.add(tab);
    tabs.push({ tab, label, purpose });
  }
  return tabs;
}

/**
 * The composition rows, in the order they arrived, keeping the ones that carry both sides.
 *
 * **A row missing either side is not carried at all**, and that is the leaf rather than a
 * tidiness rule: a row with the template's value and a blank where this agent's goes says the
 * path exists, that it was set, and that the reader may not see what to. A repeated path is
 * dropped as a repeated tab is, because the diff keys its rows on the path.
 */
export function readComposition(payload: unknown): DiffRow[] {
  if (!Array.isArray(payload)) {
    return [];
  }
  const seen = new Set<string>();
  const rows: DiffRow[] = [];
  for (const entry of payload as readonly unknown[]) {
    const fields = fieldsOf(entry);
    const part = said(fields?.["part"]);
    const path = said(fields?.["path"]);
    const template = said(fields?.["template"]);
    const instance = said(fields?.["instance"]);
    const source = said(fields?.["source"]);
    if (
      part === undefined ||
      path === undefined ||
      template === undefined ||
      instance === undefined ||
      source === undefined ||
      seen.has(path)
    ) {
      continue;
    }
    seen.add(path);
    const setBy = said(fields?.["set_by"]);
    rows.push({
      part,
      path,
      template,
      instance,
      source,
      ...(setBy === undefined ? {} : { setBy }),
    });
  }
  return rows;
}

/**
 * One agent's workspace out of a response body, or `null` when the body names no agent.
 *
 * `null` rather than a failure, and the page composes no sentence about it, which is
 * `readClassification`'s reasoning: a body that is not a workspace is a console built against
 * a different API, and the only sentence available would be one this console made up.
 */
/** A whole number from nought: a count of rows this reader was shown, or a figure in minor
 * units. Anything else is not carried, so a malformed body draws no number. */
function counted(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

/** The strings in an array, keeping the ones that say something and the order they arrived. */
function saidEach(payload: unknown): string[] {
  if (!Array.isArray(payload)) {
    return [];
  }
  const kept: string[] = [];
  for (const entry of payload as readonly unknown[]) {
    const one = said(entry);
    if (one !== undefined && !kept.includes(one)) {
      kept.push(one);
    }
  }
  return kept;
}

/**
 * The skills this agent is pinned to, keeping the ones that carry both halves of a pin.
 *
 * A skill with a name and no digest is dropped rather than drawn, for the reason a half
 * lineage is: a name with nothing under it says this agent runs a procedure whose version the
 * reader may not be told, which is a fact they did not have. A repeated name is dropped as a
 * repeated tab is, because the list is keyed on it.
 */
export function readSkills(payload: unknown): SkillPin[] {
  if (!Array.isArray(payload)) {
    return [];
  }
  const seen = new Set<string>();
  const pins: SkillPin[] = [];
  for (const entry of payload as readonly unknown[]) {
    const fields = fieldsOf(entry);
    const name = said(fields?.["name"]);
    const digest = said(fields?.["digest"]);
    if (name === undefined || digest === undefined || seen.has(name)) {
      continue;
    }
    seen.add(name);
    pins.push({ name, digest });
  }
  return pins;
}

/**
 * The connector strip, with an overflow that is only ever a number the API sent.
 *
 * A body with no strip is an empty row and no overflow, which is what a reader who reaches no
 * source is answered. A row missing its source or its presence is not carried: half a row
 * would say a connector is there whose name the reader may not have.
 */
export function readConnectors(payload: unknown): ConnectorStrip {
  const fields = fieldsOf(payload);
  const rows: ConnectorPresence[] = [];
  const shown = fields?.["shown"];
  if (Array.isArray(shown)) {
    const seen = new Set<string>();
    for (const entry of shown as readonly unknown[]) {
      const row = fieldsOf(entry);
      const source = said(row?.["source"]);
      const presence = said(row?.["presence"]);
      if (source === undefined || presence === undefined || seen.has(source)) {
        continue;
      }
      seen.add(source);
      rows.push({ source, presence });
    }
  }
  return { shown: rows, overflow: counted(fields?.["overflow"]) ?? 0 };
}

/** The surfaces offered, keeping the ones that name a channel and a profile. */
export function readChannels(payload: unknown): ChannelOffer[] {
  if (!Array.isArray(payload)) {
    return [];
  }
  const seen = new Set<string>();
  const offers: ChannelOffer[] = [];
  for (const entry of payload as readonly unknown[]) {
    const fields = fieldsOf(entry);
    const channel = said(fields?.["channel"]);
    const profile = said(fields?.["profile"]);
    if (channel === undefined || profile === undefined || seen.has(channel)) {
      continue;
    }
    seen.add(channel);
    offers.push({ channel, profile });
  }
  return offers;
}

/**
 * The figures, or nothing at all.
 *
 * Every field is required, and the basis most of all: a spend figure drawn without the label
 * saying whose it is reads as the agent's total. So a body missing any one of the four draws
 * no figures, rather than figures with a field composed here.
 */
export function readFigures(payload: unknown): AgentFigures | undefined {
  const fields = fieldsOf(payload);
  const basis = said(fields?.["basis"]);
  const range = said(fields?.["range"]);
  const spendMinor = counted(fields?.["spend_minor"]);
  const runs = counted(fields?.["runs"]);
  if (basis === undefined || range === undefined || spendMinor === undefined || runs === undefined) {
    return undefined;
  }
  return { basis, range, spendMinor, runs };
}

export function readAgentWorkspace(payload: unknown): AgentWorkspaceAnswer | null {
  const fields = fieldsOf(payload);
  const agent = readAgent(fields?.["agent"]);
  if (fields === null || agent === null) {
    return null;
  }
  const figures = readFigures(fields["headline"]);
  return {
    agent,
    tabs: readTabs(fields["tabs"]),
    composition: readComposition(fields["composition"]),
    divergent: saidEach(fields["divergent"]),
    skills: readSkills(fields["skills"]),
    connectors: readConnectors(fields["connectors"]),
    channels: readChannels(fields["channels"]),
    ...(figures === undefined ? {} : { figures }),
  };
}
