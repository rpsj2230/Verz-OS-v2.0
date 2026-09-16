/**
 * What the Skills screen asks the API for, and the three things it must not draw. No React.
 *
 * The split is `governQuery.ts`'s and `recordsQuery.ts`': this decides what may be asked and
 * what a row is, the page renders it. The reason is the case that is always wrong, and here it
 * is a column: what a screen does about a fact the API cannot send cannot be tested through a
 * component that also mounts a table.
 *
 * **This screen is SCREEN 6 of `docs/screens.html` and three of its columns have no source.**
 * The design's library lists Skill, Source, Ver, Scope, Used by, Reviewed and State. Source,
 * Reviewed and State are read off `brain.tools.skills.ImportedSkill`, Ver is the version string
 * inside the `SKILL.md`, and Scope is a department nothing records against a skill. Nothing in
 * this installation stores an imported skill, so `brain.skill_routes` sends the name, the bytes
 * each agent is pinned to and which agents pin them, and it sends `review_is_not_recorded` to
 * say why the rest is missing. See `A_COLUMN_THAT_CAN_ONLY_BE_BLANK_MAKES_A_CLAIM_THE_DATA_DOES_NOT`.
 *
 * **There is no import control and no assign control, and this module has no path one could be
 * posted to.** The design's bar offers Paste URL, Connect repo and Write in Studio, and its
 * review pane offers Approve and Reject. Every one of those is a write, the API declares none,
 * and a button whose press is refused every time is worse than no button. See
 * `A_CONTROL_WITH_NO_ROUTE_BEHIND_IT_IS_A_BUTTON_THAT_LIES`.
 *
 * **Nothing here decides who may see what.** The request is identical for every caller, the API
 * answers from grants this browser never receives, and a refusal comes back as a value rendered
 * in the API's own words. This console holds no rule about skills.
 *
 * **No number about the rows is rendered.** Not a total, not a page number, not the count of
 * what arrived. The listing is filtered per caller, so a figure is the subtraction `CLAUDE.md`
 * forbids. The one count on the page is the review queue's, which `brain.console.govern_estate.
 * skill_queue` computes over exactly the entries listed beneath it and never over a wider list.
 *
 * Task ids: M42.6.4
 */

import type { components } from "../api/schema";

/** One skill and the agents pinned to it, as `brain.skill_routes.SkillRow` sends it. */
export type SkillLibraryRow = components["schemas"]["SkillRow"];
/** One agent and the bytes of a skill it runs, as `SkillPinView` sends it. */
export type SkillPin = components["schemas"]["SkillPinView"];
/** One skill waiting for a reviewer, as `QueueEntryView` sends it. */
export type SkillQueueRow = components["schemas"]["QueueEntryView"];

/**
 * Written down because an absent column is the thing a reader of this screen will ask about
 * first, and the wrong answer to it is to draw the column empty.
 */
export const A_COLUMN_THAT_CAN_ONLY_BE_BLANK_MAKES_A_CLAIM_THE_DATA_DOES_NOT =
  "SCREEN 6 puts Source, Ver, Scope, Reviewed and State beside every skill, and each of them " +
  "is read off an imported skill this installation does not store. A column rendered with " +
  "nothing in it looks like the design and says something the design does not: a Reviewed " +
  "column blank on every row reads as nobody having reviewed anything, and a State column " +
  "blank on every row reads as every skill being unreviewed. So the columns are absent, and " +
  "the page says once, in words, which facts are missing and why.";

/**
 * Written down because the design's bar is full of controls and every one of them is a write.
 */
export const A_CONTROL_WITH_NO_ROUTE_BEHIND_IT_IS_A_BUTTON_THAT_LIES =
  "Paste URL, Connect repo, Write in Studio, Approve and Reject are all writes, and the API " +
  "declares none of them: there is no store an imported skill could be written to, and " +
  "brain.console.workspace_capabilities.attach_skill refuses to pin anything but a skill a " +
  "named person approved. A console that drew the buttons anyway would be a screen whose every " +
  "control is refused, which teaches a person that refusals are normal. The page says what " +
  "cannot be done here instead of offering it.";

/** Where the API keeps this screen. */
export const SKILLS_API_PATH = "/skills";

/** The console addresses. The second is one skill open. */
export const SKILLS_PATH = "/skills";

/** The one query parameter the route declares. */
export const LIMIT_PARAMETER = "limit";

/**
 * How many agents to assemble the catalogue from.
 *
 * Below the route's declared maximum, which `tests/skills-page.test.tsx` reads out of the API's
 * own document rather than comparing with another constant here: a console asking for more than
 * a route admits is refused with `HTTPValidationError`, which reaches a person as the least
 * useful sentence this console has, and it would do so on every load.
 */
export const SKILLS_PAGE_SIZE = 200;

/** The whole request this screen makes, query string included. */
export function skillsApiPath(): string {
  return `${SKILLS_API_PATH}?${LIMIT_PARAMETER}=${String(SKILLS_PAGE_SIZE)}`;
}

/**
 * The console address for one skill's page.
 *
 * Built from a constant prefix and an encoded name, for the reason `governQuery.subjectAddress`
 * gives: GHSA-wrjc-x8rr-h8h6 is an open redirect through a backslash reaching `<Link>` and
 * `useNavigate`, it covers every react-router this project can install, and what holds the
 * defence up is the literal first segment rather than the encoding.
 */
export function skillAddress(name: string): string {
  return `${SKILLS_PATH}/${encodeURIComponent(name)}`;
}

/** One page of skills, as this console holds it. */
export interface SkillsPage {
  readonly skills: readonly SkillLibraryRow[];
  readonly queue: readonly SkillQueueRow[];
  /** The queue's own counts, over exactly the entries above. */
  readonly waiting: number;
  readonly edits: number;
  readonly stale: number;
  /** The load came back full. Never how much more there is. */
  readonly truncated: boolean;
  /** No imported skill is stored, so no row carries a source, a version or a state. */
  readonly reviewIsNotRecorded: boolean;
  /** There is no route that assigns a skill to an agent. */
  readonly assignmentIsNotWritable: boolean;
}

const NOTHING: SkillsPage = Object.freeze({
  skills: [],
  queue: [],
  waiting: 0,
  edits: 0,
  stale: 0,
  truncated: false,
  // True on an unreadable body as well as on a real one, because both of the facts they stand
  // for are true of this installation, and a page that dropped the sentences when a response
  // came back in an unexpected shape would drop them exactly when it understood least.
  reviewIsNotRecorded: true,
  assignmentIsNotWritable: true,
});

/**
 * Read `brain.skill_routes.SkillsPage` out of a response body.
 *
 * **`total` and `next_cursor` stop here**, in the way `readPeoplePage` stops them: not an
 * agreement not to render the total but no path from the payload to a renderer.
 *
 * An unreadable body yields an empty page rather than throwing, which is `readMatrixPage`'s
 * choice and for its reason: the shape is fixed by a response model in this repository, so a
 * body that is not a page is a console built against a different API.
 */
export function readSkillsPage(payload: unknown): SkillsPage {
  if (typeof payload !== "object" || payload === null) {
    return NOTHING;
  }
  const body = payload as {
    items?: unknown;
    queue?: unknown;
    truncated?: unknown;
    review_is_not_recorded?: unknown;
    assignment_is_not_writable?: unknown;
  };
  if (!Array.isArray(body.items)) {
    return NOTHING;
  }
  const queue = body.queue as
    | { entries?: unknown; waiting?: unknown; edits?: unknown; stale?: unknown }
    | undefined;
  return {
    skills: body.items as SkillLibraryRow[],
    queue: Array.isArray(queue?.entries) ? (queue.entries as SkillQueueRow[]) : [],
    waiting: typeof queue?.waiting === "number" ? queue.waiting : 0,
    edits: typeof queue?.edits === "number" ? queue.edits : 0,
    stale: typeof queue?.stale === "number" ? queue.stale : 0,
    truncated: body.truncated === true,
    reviewIsNotRecorded: body.review_is_not_recorded !== false,
    assignmentIsNotWritable: body.assignment_is_not_writable !== false,
  };
}

/** The skill with this name among the ones on the page, or null. */
export function skillIn(
  skills: readonly SkillLibraryRow[],
  name: string,
): SkillLibraryRow | null {
  return skills.find((one) => one.name === name) ?? null;
}

/**
 * The rows whose agents do not all run the same bytes.
 *
 * The design's upstream-drift card, computed from what this install records rather than from a
 * repository it cannot reach: what is knowable here is that two agents under one skill name are
 * pinned to two different digests, which is the same fact arriving from inside.
 */
export function driftingRows(skills: readonly SkillLibraryRow[]): readonly SkillLibraryRow[] {
  return skills.filter((one) => one.versions_differ);
}
