/**
 * The fixtures more than one module's page cases answer with, and the shape of a case.
 *
 * **Only what two modules share lives here.** A fixture that one module's pages alone answer with
 * sits in that module's file under `pageCases/`, so rebuilding a module edits its own file and no
 * other. This is the remainder, and the module files import it, never `pageCases.ts`: that file
 * reads every module file eagerly, so a module file importing it back would read its constants
 * before they exist.
 *
 * The values are identifier-shaped tokens with nowhere to break, because that is what the phone
 * test needs, and the state test does not care what the values are.
 *
 * Task ids: none
 */

/** A value with nowhere to break, which is what an identifier from the API usually is. */
export const UNBROKEN = `UNBROKEN${"x".repeat(72)}`;

export const RUNG_ID = "11111111-1111-4111-8111-111111111111";

export interface PageCase {
  /** The address mounted for this pattern. */
  readonly address: string;
  /** Whether the page sits behind the session guard and so needs a signed-in console. */
  readonly signedIn: boolean;
  /** The stand-in API, by path. */
  readonly answers: Readonly<Record<string, unknown>>;
  /** Whether the page draws a value the API sent, so the unbroken value must appear on it. */
  readonly drawsValues: boolean;
}

export const MATRIX = {
  items: [
    {
      id: RUNG_ID,
      tier: "main",
      position: 0,
      role: "primary",
      scope: {},
      deployment_id: UNBROKEN,
      provider: "anthropic",
      model: "claude-sonnet-5",
      attempts: 1,
      timeout_seconds: 12,
      max_concurrency: 40,
      enabled: true,
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  editable: true,
};

/** One scope, whose slug and whose clause value are both unbreakable tokens. */
export const SCOPES = {
  items: [
    {
      slug: UNBROKEN,
      label: UNBROKEN,
      is_department: true,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  departments: [UNBROKEN],
  staleness: null,
};

/**
 * One skill, whose name, whose pinned digest and whose agent are all unbreakable tokens.
 *
 * A digest is sixty-four characters with nowhere to break and it is on every row of this
 * screen, which makes it the widest single value the console renders anywhere.
 */
/**
 * One ledger entry whose actor, subject and detail are unbreakable tokens, and the same actor
 * offered in the Who filter, which is the one value on the page outside the table.
 */
export const AUDIT = {
  items: [
    {
      at: "2019-03-04T09:00:00Z",
      action: "grant",
      actor_id: UNBROKEN,
      subject_kind: "principal",
      subject_id: UNBROKEN,
      details: { capability: UNBROKEN },
    },
  ],
  next_cursor: null,
  order: "newest",
  actions: ["grant"],
  subject_kinds: ["principal"],
  actors: [UNBROKEN],
};
