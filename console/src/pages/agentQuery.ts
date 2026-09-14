/**
 * What the agent page asks the API for, and how an answer becomes the shapes the workspace
 * draws.
 *
 * **No route in this repository answers this address yet, and that is stated here rather than
 * left to be discovered.** `brain.agents.model`, `brain.agents.template` and
 * `brain.agents.upgrade` each record that no HTTP route calls them, and
 * `brain.console.workspace` builds the strip, the deep link and the composition parts with no
 * route behind any of them. So every agent this page is opened on answers 404 today, and the
 * page renders the API's own sentence for it, which is the sentence it renders for an agent
 * the reader may not see. That is the honest direction to fail in: the page never draws a fact
 * nobody sent. See `NO_ROUTE_ANSWERS_THE_WORKSPACE_ADDRESS_YET`. `tests/agent-page.test.tsx`
 * reads the API's own document and goes red on the day it declares the route, because that is
 * the day this reader has to be checked against a declared schema.
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

/**
 * Written down because the page is reachable and no agent will render on it until a route
 * exists, which is a state somebody will otherwise read as a bug in the console.
 */
export const NO_ROUTE_ANSWERS_THE_WORKSPACE_ADDRESS_YET =
  "This page asks the API for one agent's workspace at an address no route in this " +
  "repository serves, so every agent answers 404 and the page shows the API's own sentence, " +
  "which is the sentence it shows for an agent the reader may not see. Nothing is invented " +
  "to fill the gap: the header, the strip and the diff draw only what an answer carried. " +
  "When a route lands, the wire names this reader copies are checked against its declared " +
  "schema rather than against the Python models they were taken from.";

/** Where one agent's workspace is asked for, under the API base. See the note above. */
export function agentWorkspaceApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/workspace`;
}

/** One agent's workspace, as this console holds it. Three fields, and none of them a count. */
export interface AgentWorkspaceAnswer {
  readonly agent: AgentIdentity;
  /** The strip, in the order the API answered it. */
  readonly tabs: readonly WorkspaceTabView[];
  /** The composition beside its template, path by path, in the order the API answered it. */
  readonly composition: readonly DiffRow[];
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
  const templateId = said(fields["template_id"]);
  const version = pinnedVersion(fields["template_version"]);
  return {
    agentId,
    displayName,
    ...(roleLine === undefined ? {} : { roleLine }),
    ...(ownerId === undefined ? {} : { ownerId }),
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
export function readAgentWorkspace(payload: unknown): AgentWorkspaceAnswer | null {
  const fields = fieldsOf(payload);
  const agent = readAgent(fields?.["agent"]);
  if (fields === null || agent === null) {
    return null;
  }
  return {
    agent,
    tabs: readTabs(fields["tabs"]),
    composition: readComposition(fields["composition"]),
  };
}
