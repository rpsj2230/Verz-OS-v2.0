/**
 * What an agent's workspace is made of, as shapes, and the two rules those shapes keep.
 *
 * Nothing here renders and nothing here fetches. It is the vocabulary the three components
 * beside it are written against, kept in one file for the reason `src/ui/tone.ts` is kept
 * apart from the components that use it: the rules below are properties of the *shapes*,
 * and a property of a shape can be checked by reading the shape rather than by trusting
 * every renderer that will ever be written against it.
 *
 * **A field a reader may not be told about and a field that is not there are one absence,
 * and the type is how that is kept true.** `tsconfig.json` turns on
 * `exactOptionalPropertyTypes`, so an optional property here is genuinely absent or
 * genuinely present: there is no `{ ownerId: undefined }` in between. The API suppresses
 * the key in both cases, exactly as `brain.console.workspace.tab_strip` returns one tuple
 * for a tab the caller holds no grant for and a tab with nothing in it. So there is no
 * value a renderer could branch on to tell the two apart, and no renderer has to remember
 * not to. See `AN_ABSENT_FIELD_AND_A_WITHHELD_ONE_ARE_ONE_ABSENCE`.
 *
 * **No shape here has anywhere to put a count of what was left out.** Not a total, not a
 * remainder, not a number of tabs, not a number of rows. `brain.ops.jobs.
 * hidden_count_fields` is the same check made of the Python surfaces, over a list of the
 * names such a field arrives under, and `tests/agent-workspace.test.tsx` reads that list
 * out of the Python source and asks it of the interfaces below. A list written here would
 * be a copy that stops matching the day somebody adds a name there.
 *
 * **The vocabularies come from the Python side wherever the Python side has one.** The
 * address prefix is `brain.console.workspace.DEEP_LINK_PREFIX`, the tab keys are its `Tab`,
 * the composition parts are the values of its `PART_OF_PATH`, and a diff row's source is
 * `brain.agents.template.FieldSource`. Each is a copy, because there is no shared artefact
 * between a Python package and a browser bundle, and each is checked against the original
 * for the reason `tests/support/repo.ts` exists: a constant compared against itself is
 * green for every value it could hold.
 *
 * The one vocabulary this file owns is the pane, because nothing on the Python side names
 * it. M39.1.2.3 names two panes and there are two.
 *
 * Task ids: M39.1.1.5, M39.1.2.1, M39.1.2.3, M39.1.2.5
 */

/**
 * Where an agent's workspace is addressed, copied from
 * `brain.console.workspace.DEEP_LINK_PREFIX`.
 *
 * The trailing slash is part of it there, and it is part of it here, because `resolve`
 * refuses a link that does not start with exactly this string and a prefix wrong by one
 * character is a link that resolves to nothing with nothing saying why.
 */
export const AGENT_ADDRESS_PREFIX = "/agents/";

/** Where the roster is: the prefix without the separator that introduces one agent. */
export const ROSTER_ADDRESS = "/agents";

/**
 * The address of one tab of one agent, spelled as `brain.console.workspace.deep_link`
 * spells it.
 *
 * This composes an address and never decides whether it resolves. `resolve` answers `None`
 * to all five of its failures, and a console that guessed which of them had happened would
 * be the oracle that function exists to refuse.
 */
export function tabAddress(agentId: string, tab: string): string {
  return `${AGENT_ADDRESS_PREFIX}${agentId}/${tab}`;
}

/**
 * The three ids the workspace's markup wires itself together with.
 *
 * Derived from the agent and the tab rather than counted, so nothing in the DOM is an
 * ordinal: `aria-controls="agent-tab-3"` would put the position of a tab in the strip into
 * an attribute, and the position of a tab in a strip that was narrowed for this reader is
 * the one number the strip exists not to publish.
 */
export function headingId(agentId: string): string {
  return `agent-${agentId}-name`;
}

export function tabId(agentId: string, tab: string): string {
  return `agent-${agentId}-tab-${tab}`;
}

export function panelId(agentId: string, tab: string): string {
  return `agent-${agentId}-panel-${tab}`;
}

/**
 * The two things the right pane can be showing. Closed, and short, in the spelling
 * `src/ui/tone.ts` uses for its own closed vocabulary.
 *
 * There is deliberately no third member. A pane meaning "whatever was there last" is a
 * state nobody chose, and a pane meaning "none" would make an empty right-hand column a
 * thing a reader has to interpret.
 */
export const PANES = ["dashboard", "profile"] as const;

export type Pane = (typeof PANES)[number];

/** Where the right pane starts. The figures, because they are what an agent is opened for. */
export const FIRST_PANE: Pane = "dashboard";

/**
 * Written down because "show the label and leave the value blank" is the change that would
 * look like tidiness in review and would be the whole leak.
 */
export const AN_ABSENT_FIELD_AND_A_WITHHELD_ONE_ARE_ONE_ABSENCE =
  "A header row with a label and no value under it says this agent has an owner, or a " +
  "template, that the reader may not be told about, which is a fact they did not have and " +
  "did not ask for. A dash, an em space, the word unknown and a lock all say it too. So " +
  "an absent field contributes no element at all: the label goes with the value, and an " +
  "agent whose owner is withheld renders exactly as an agent that has none. The lock is " +
  "for a field inside a record whose existence was already disclosed, which is a different " +
  "rule and is argued in src/ui/Lock.tsx; a header is the record.";

/**
 * Written down because the half-lineage is the version anybody would write first.
 */
export const A_LINEAGE_IS_A_TEMPLATE_AND_A_VERSION_OR_IT_IS_NEITHER =
  "A version with no template beside it says there is a template this reader may not be " +
  "told the name of, and a template with no version says the same thing about the pin. " +
  "Both are the count of hidden things spelled out in words rather than in digits. So " +
  "lineage is one optional value carrying both fields and there is no shape in which one " +
  "of them is missing.";

/**
 * Written down because comparing the two columns is how anybody would implement a diff,
 * and here it is wrong in a case the Python side names explicitly.
 */
export const DIVERGENCE_IS_READ_FROM_THE_OVERLAY_AND_NEVER_FROM_TWO_VALUES =
  "brain.agents.upgrade says a path where both answers coincide is still a conflict: if " +
  "the template happens to say what this install already set, the values match and the " +
  "decision is not empty, because giving the path back means the next version moves it " +
  "silently. brain.console.workspace.divergent_parts reads the overlay for the same " +
  "reason, and never the values. A console that decided divergence by comparing the two " +
  "columns would therefore disagree with both, in exactly the case they were written to " +
  "cover, and it would look correct on every row a reader happened to check.";

/**
 * One template an agent was installed from. Both fields, always. See
 * `A_LINEAGE_IS_A_TEMPLATE_AND_A_VERSION_OR_IT_IS_NEITHER`.
 */
export interface TemplateLineage {
  /** The template's own identifier, as `brain.agents.template.TemplateInstance` spells it. */
  readonly templateId: string;
  /** The published version this agent is pinned to. */
  readonly version: number;
}

/**
 * The agent a header is about, as the API answered it for this reader.
 *
 * Two required fields and three optional ones, and the split is the disclosure decision.
 * An agent that reached this console at all is one the reader's audience covers, so its id
 * and its name are facts they already have. The other three are separate questions with
 * separate answers, and the key is absent when the answer is no.
 */
export interface AgentIdentity {
  readonly agentId: string;
  /** `brain.agents.model.AgentRecord.display_name`. */
  readonly displayName: string;
  /**
   * One sentence saying what this agent is for.
   *
   * Supplied whole. The console does not cut one out of the persona: a persona is prompt
   * material up to `PERSONA_CHARS`, and a first line taken from it here would be a summary
   * this browser composed out of an instruction it has no business reading.
   * `brain.agents.template.ManifestIdentity.summary` is the field that is already a
   * sentence in a picker.
   */
  readonly roleLine?: string;
  /**
   * Who answers for this agent now: `AgentAudience.owner_id`, the current steward.
   *
   * Not `created_by`. `brain.agents.model` keeps those apart on purpose, because after a
   * transfer the record still says who built the thing and says who answers for it now,
   * and a header showing the wrong one of the two is a header naming somebody who has not
   * been responsible for this agent for a year.
   */
  readonly ownerId?: string;
  readonly lineage?: TemplateLineage;
}

/**
 * One tab of the strip, as `brain.console.workspace.tab_strip` decided it.
 *
 * The strip arrives already narrowed: a tab the caller holds no grant for and a tab with
 * nothing in it are both simply not in the list. This console does not filter it again and
 * has nothing to filter it with.
 */
export interface WorkspaceTabView {
  /** The key, from `brain.console.workspace.Tab`. */
  readonly tab: string;
  /** The tab's own label. The API's word, rendered as it arrived. */
  readonly label: string;
  /** `WorkspaceTab.purpose`: one sentence, so the strip explains itself. */
  readonly purpose: string;
}

/**
 * What a composition diff row says a value's current source is, copied from
 * `brain.agents.template.FieldSource`.
 *
 * The one member this console acts on. The other, `template`, is the absence of this one,
 * and a word neither of them is renders as itself and is treated as neither: that is
 * `src/ui/Status.tsx`'s rule about a state nobody here has heard of, and the direction it
 * fails in matters, because inventing "set here" for an unknown word would mark a row as
 * locally edited on no evidence.
 */
export const SET_ON_THIS_AGENT = "instance";

/**
 * One path of one agent's composition, with both sides of it (M39.1.1.5).
 *
 * **Both values are required and there is no shape with one of them.** A row saying a path
 * differs while withholding what it differs to is the disclosure this whole surface is
 * arranged against: it tells the reader a value exists, that it was changed, and that they
 * may not have it, which is three facts more than silence. A path whose value the reader
 * may not see is therefore not a row at all, and nothing anywhere counts the rows that did
 * not arrive. See `A_DIFF_ROW_CARRIES_BOTH_SIDES_OR_IT_IS_NOT_A_ROW`.
 *
 * Both sides arrive as text. The Python side has one canonical spelling of a manifest
 * value, `brain.agents.template.canonical`, and a browser that formatted two equal JSON
 * values with its own key order would show a difference that is not there, in the column
 * whose whole job is to show differences.
 */
export interface DiffRow {
  /**
   * Which part of the composition this path supplies, from the values of
   * `brain.console.workspace.PART_OF_PATH`. Rendered as it arrived.
   */
  readonly part: string;
  /** The manifest path, from `brain.agents.template.MANIFEST_PATHS`. */
  readonly path: string;
  /** What the template this agent was installed from says, canonically spelled. */
  readonly template: string;
  /** What this agent has, canonically spelled. */
  readonly instance: string;
  /** `FieldOwner.source`: who supplies the value in force. See `SET_ON_THIS_AGENT`. */
  readonly source: string;
  /**
   * Who last set the local value, when the reader may be told.
   *
   * Absent when nobody set one and absent when the reader may not be told who did, which
   * is the same absence every optional field here keeps. There is no companion date: a
   * date needs a locale and a zone this console does not decide, and the question a
   * composition diff answers is who set this, not when.
   */
  readonly setBy?: string;
}

/**
 * Written down because a row with one column filled in is the shape a well meaning
 * renderer produces when it is handed a value it may not show.
 */
export const A_DIFF_ROW_CARRIES_BOTH_SIDES_OR_IT_IS_NOT_A_ROW =
  "A diff that shows a path, marks it changed, and leaves the value out has told the " +
  "reader that something exists, that somebody changed it, and that they are not allowed " +
  "to see it. Silence tells them none of the three. So a path whose value is withheld is " +
  "absent from the rows entirely, both columns are required, and there is nowhere in the " +
  "table or around it for a count of the rows that did not arrive.";

/** What this workspace is holding while somebody uses it. Two fields, and no third. */
export interface WorkspaceState {
  /** Which tab the main area is showing. A key from the strip it was given. */
  readonly tab: string;
  /** Which of the two views the right pane is showing. */
  readonly pane: Pane;
}

/**
 * The two things somebody can do to that state.
 *
 * A discriminated union rather than two setters, because the property M39.1.2.3 asks for
 * is about what one action leaves alone, and that is a claim about a transition. Two
 * setters have no transition to make the claim about.
 */
export type WorkspaceAction =
  | { readonly kind: "select-tab"; readonly tab: string }
  | { readonly kind: "show-pane"; readonly pane: Pane };

/**
 * The next state (M39.1.2.3).
 *
 * **`show-pane` writes the pane and copies the rest, and that is the whole leaf in one
 * line.** See `SWITCHING_THE_RIGHT_PANE_MOVES_NOTHING_BUT_THE_RIGHT_PANE`. The property is
 * asserted over arbitrary sequences of actions rather than over one switch, because the
 * failure this guards against is not a reducer that resets the tab on the first switch: it
 * is one that resets it under some combination nobody tried by hand.
 *
 * Pure, and the component holds it through `useReducer`, so the same transition is
 * checkable without rendering anything and observable when something is rendered. The
 * rendered half is the one the reducer cannot see: a layout that puts the tab panel inside
 * each pane's branch keeps this state perfectly and remounts the panel underneath it.
 */
export function reduce(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
  switch (action.kind) {
    case "select-tab":
      return { tab: action.tab, pane: state.pane };
    case "show-pane":
      return { tab: state.tab, pane: action.pane };
  }
}

/**
 * Written down because the reducer is one line and the rule it keeps is the leaf.
 */
export const SWITCHING_THE_RIGHT_PANE_MOVES_NOTHING_BUT_THE_RIGHT_PANE =
  "Somebody reading a conversation opens the profile to check which template the agent " +
  "came from, and comes back. If the tab moved while they were gone they are now reading " +
  "a different tab and nothing told them, and if the panel was rebuilt they have lost " +
  "whatever they had open in it. So a pane action writes the pane and copies everything " +
  "else, and the panel is rendered in one place rather than once inside each pane, " +
  "because a conditional that swaps the subtree keeps the state and destroys the DOM " +
  "holding it.";

/**
 * Written down because the obvious implementation of "back to the roster" is a navigation
 * performed from a key handler.
 */
export const THE_WAY_BACK_IS_A_LINK_AND_NEVER_A_NAVIGATION_THIS_COMPONENT_PERFORMS =
  "A key handler that navigated would take the decision away from the router that owns " +
  "the address, and it would swallow the key for everything nested inside the workspace: " +
  "a dialog, a menu and a form all want Escape too, and the one that gets it is whichever " +
  "listener was registered. So the way back is an ordinary link, placed before the strip " +
  "so that shift and tab reach it with no handler at all, and Escape moves focus to it " +
  "rather than following it. Focus is reversible and navigation is not.";

/**
 * Which tab a strip should open on, given where a deep link asked to land.
 *
 * Falls back to the first tab in the strip, silently, and the silence is the point: a
 * sentence explaining that the requested tab is not there would answer the question
 * `brain.console.workspace.resolve` returns `None` to, which is whether that tab exists
 * and this reader may not see it. An empty strip has no tab to open and returns the empty
 * string, which the component renders as no panel and says nothing about.
 */
export function openingTab(tabs: readonly WorkspaceTabView[], wanted?: string): string {
  const asked = tabs.find((one) => one.tab === wanted);
  if (asked) {
    return asked.tab;
  }
  return tabs[0]?.tab ?? "";
}

/**
 * The tab one arrow key away, wrapping at both ends.
 *
 * Wrapping is the WAI-ARIA tabs behaviour and is what makes a strip navigable without
 * counting: the right arrow from the last tab is the first tab, so nobody has to know how
 * many there are. Returns the tab it was given when the strip holds one tab or none, so a
 * key press is never a move to nothing.
 */
export function tabByStep(
  tabs: readonly WorkspaceTabView[],
  current: string,
  step: number,
): string {
  if (tabs.length === 0) {
    return current;
  }
  const at = tabs.findIndex((one) => one.tab === current);
  // A current tab the strip does not hold is the deep-link case again, and the answer is
  // the same one `openingTab` gives: start at the beginning rather than refusing to move.
  const from = at === -1 ? 0 : at;
  const next = (from + step + tabs.length) % tabs.length;
  return tabs[next]?.tab ?? current;
}

/**
 * The letters an agent's avatar shows.
 *
 * **An avatar is the one thing in the header with no fact behind it**, and that is why it
 * is computed from the name rather than fetched. `brain.agents.model.AgentRecord` has no
 * image column and nothing in this repository stores one, so a picture would arrive as a
 * URL, which is a second fact about the agent and a request to somewhere this console does
 * not control. Initials of the name already on the screen add nothing the reader does not
 * already have, which is what makes them safe to draw beside a name that may be all the
 * reader is allowed.
 *
 * Two letters at most, from the first and last words, and one letter when there is one
 * word. Upper cased with an explicit locale, so the result does not depend on the browser's:
 * the Turkish dotless i turns a lower case i into a different letter under a Turkish locale,
 * and an avatar that differs by the reader's machine is a difference two people comparing
 * screens can see.
 */
export function initials(displayName: string): string {
  const words = displayName.split(/\s+/u).filter((word) => word.length > 0);
  const first = words[0] ?? "";
  const last = words.length > 1 ? (words[words.length - 1] ?? "") : "";
  return `${first.slice(0, 1)}${last.slice(0, 1)}`.toLocaleUpperCase("en-GB");
}
