/**
 * What the Credentials module asks `brain.credential_routes` for, and how each answer is read. No
 * React.
 *
 * **No field on any answer could hold a value, and nothing here asks for one.** A row says whether a
 * value is held and when it was written, never the value, its length or any part of it; the API has
 * no field that could carry one (`brain.credential_routes.CredentialRow`), and these readers keep
 * only the fields they name, so a field added to the API later is not drawn until somebody reads it
 * here on purpose.
 *
 * **Every reader keeps only what was sent.** A row is kept with its slot, holder and kind, once, in
 * the order it came; every other field is carried only when it arrived in its own shape, so a field
 * the API left out is left out of the page rather than drawn as a default. A figure the API sent as
 * null is "not recorded yet" on the page, never nought.
 *
 * Task ids: M27.11.10, M27.15.50
 */

/** Where the API keeps the list; one slot is below it as `{family}/{name}`. */
export const CREDENTIALS_API_PATH = "/credentials";

/** The console's address for the list, and the menu's label for it. */
export const CREDENTIALS_ADDRESS = "/credentials";

/** One slot's address in the API, from its path as the row carries it. */
export function credentialApiPath(slot: string): string {
  return `${CREDENTIALS_API_PATH}/${slot.split("/").map(encodeURIComponent).join("/")}`;
}

/** One slot's page. The Dashboard is the bare address. */
export function credentialAddress(slot: string): string {
  return `${CREDENTIALS_ADDRESS}/${slot.split("/").map(encodeURIComponent).join("/")}`;
}

/** What the vault is, as the list and every slot's page are told. */
export interface VaultOverview {
  readonly seal: string;
  readonly told: string;
  readonly slotsUnread: string;
  readonly tokenPolicy: string;
  readonly tokenPolicies: readonly string[];
  readonly tokenTold: string;
  readonly liveReads: string;
  readonly liveReadsTold: string;
}

/** One slot on the list. */
export interface CredentialRow {
  readonly slot: string;
  readonly holder: string;
  readonly kind: string;
  readonly state: string;
  /** Absent when the vault could not be asked: not known, never "not held". */
  readonly held?: boolean;
  readonly setAt?: string;
  readonly outrankedBy?: string;
  readonly readBy?: string;
  readonly writable: boolean;
  readonly writeTold: string;
}

/** One field a slot's form asks for. */
export interface CredentialField {
  readonly field: string;
  readonly label: string;
  readonly accepts: string;
}

/** One write the ledger holds. */
export interface CredentialChange {
  readonly at: string;
  readonly by: string;
  readonly byId: string;
}

/** One slot's page. */
export interface CredentialDetail {
  readonly vault: VaultOverview | null;
  readonly row: CredentialRow;
  readonly description: string;
  readonly fields: readonly CredentialField[];
  readonly askFor: readonly string[];
  readonly never: readonly string[];
  readonly takesEffect: string;
  readonly takesEffectTold: string;
  readonly useRecorded: boolean;
  readonly lastUsedAt?: string;
  readonly lastUsedTold: string;
  /** Null when the API could not read the ledger; `historyTold` says why. */
  readonly history: readonly CredentialChange[] | null;
  readonly historyTold: string;
}

type Loose = Readonly<Record<string, unknown>>;

function record(value: unknown): Loose | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Loose) : undefined;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function words(value: unknown): readonly string[] {
  return Array.isArray(value) ? value.filter((one): one is string => typeof one === "string" && one !== "") : [];
}

/** The vault's overview out of a body carrying one under `vault`, or null. */
export function readVaultOverview(payload: unknown): VaultOverview | null {
  const vault = record(record(payload)?.["vault"]);
  const seal = said(vault?.["seal"]);
  if (vault === undefined || seal === undefined) {
    return null;
  }
  return {
    seal,
    told: text(vault["told"]),
    slotsUnread: text(vault["slots_unread"]),
    tokenPolicy: text(vault["token_policy"]),
    tokenPolicies: words(vault["token_policies"]),
    tokenTold: text(vault["token_told"]),
    liveReads: text(vault["live_reads"]),
    liveReadsTold: text(vault["live_reads_told"]),
  };
}

/** One row, or undefined when it lacks the three fields every row has. */
export function readRow(value: unknown): CredentialRow | undefined {
  const entry = record(value);
  const slot = said(entry?.["slot"]);
  const holder = said(entry?.["holder"]);
  const kind = said(entry?.["kind"]);
  if (entry === undefined || slot === undefined || holder === undefined || kind === undefined) {
    return undefined;
  }
  const held = entry["held"];
  const setAt = said(entry["set_at"]);
  const outrankedBy = said(entry["outranked_by"]);
  const readBy = said(entry["read_by"]);
  return {
    slot,
    holder,
    kind,
    state: said(entry["state"]) ?? "unknown",
    ...(typeof held === "boolean" ? { held } : {}),
    ...(setAt === undefined ? {} : { setAt }),
    ...(outrankedBy === undefined ? {} : { outrankedBy }),
    ...(readBy === undefined ? {} : { readBy }),
    writable: entry["writable"] === true,
    writeTold: text(entry["write_told"]),
  };
}

/** The rows out of the list's body, once each, in the order they came. */
export function readCredentialRows(payload: unknown): readonly CredentialRow[] {
  const items = record(payload)?.["items"];
  if (!Array.isArray(items)) {
    return [];
  }
  const seen = new Set<string>();
  const rows: CredentialRow[] = [];
  for (const item of items as readonly unknown[]) {
    const row = readRow(item);
    if (row === undefined || seen.has(row.slot)) {
      continue;
    }
    seen.add(row.slot);
    rows.push(row);
  }
  return rows;
}

/** One slot's page out of its body, or null when it is not one. */
export function readCredentialDetail(payload: unknown): CredentialDetail | null {
  const body = record(payload);
  const row = readRow(body?.["row"]);
  if (body === undefined || row === undefined) {
    return null;
  }
  const fields: CredentialField[] = [];
  for (const one of Array.isArray(body["fields"]) ? (body["fields"] as readonly unknown[]) : []) {
    const entry = record(one);
    const field = said(entry?.["field"]);
    if (entry !== undefined && field !== undefined) {
      fields.push({ field, label: said(entry["label"]) ?? field, accepts: text(entry["accepts"]) });
    }
  }
  const history = Array.isArray(body["history"])
    ? (body["history"] as readonly unknown[]).flatMap((one) => {
        const entry = record(one);
        const at = said(entry?.["at"]);
        return entry === undefined || at === undefined ? [] : [{ at, by: text(entry["by"]), byId: text(entry["by_id"]) }];
      })
    : null;
  const lastUsedAt = said(body["last_used_at"]);
  return {
    vault: readVaultOverview(body),
    row,
    description: text(body["description"]),
    fields,
    askFor: words(body["ask_for"]),
    never: words(body["never"]),
    takesEffect: text(body["takes_effect"]),
    takesEffectTold: text(body["takes_effect_told"]),
    useRecorded: body["use_recorded"] === true,
    ...(lastUsedAt === undefined ? {} : { lastUsedAt }),
    lastUsedTold: text(body["last_used_told"]),
    history,
    historyTold: text(body["history_told"]),
  };
}

// ------------------------------------------------------------------------------ words

/** What each kind of slot is, as a person reads it. */
export const KIND_WORDS: Readonly<Record<string, string>> = Object.freeze({
  provider: "Model provider",
  relay: "Mail relay",
  store: "Object store",
  connector: "Connected source",
  channel: "Channel",
});

/** A slot's state in words. `defined` is a source's slot made at install with no key yet. */
export const STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  held: "Held",
  defined: "Defined, empty",
  empty: "Empty",
  unknown: "Not known",
});

/** Which process reads a slot's value. */
export const READ_BY_WORDS: Readonly<Record<string, string>> = Object.freeze({
  application: "The application",
  worker: "The worker",
});

/** The seal, at a glance; the API's sentence says what to do. */
export const SEAL_WORDS: Readonly<Record<string, string>> = Object.freeze({
  absent: "No vault",
  unreachable: "Not answering",
  uninitialised: "Never initialised",
  sealed: "Sealed",
  open: "Unsealed",
});

export function kindWords(kind: string): string {
  return KIND_WORDS[kind] ?? kind;
}

export function stateWords(state: string): string {
  return STATE_WORDS[state] ?? state;
}

export function sealWords(seal: string): string {
  return SEAL_WORDS[seal] ?? seal;
}

/** An instant as a person reads it, in UTC so two people comparing screens see one time. */
export function whenWords(stamp: string | undefined): string | undefined {
  if (stamp === undefined) {
    return undefined;
  }
  const at = new Date(stamp);
  return Number.isNaN(at.getTime()) ? undefined : `${at.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}
