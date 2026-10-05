/**
 * What the Connectors module asks the API for and how it reads the answers. No React.
 *
 * **Three reads and three writes, each the API's.** The list is `GET /api/v1/console/connectors`
 * (`brain.connector_routes.connector_sources`, over the list contract), one source's page is
 * `GET /api/v1/console/connectors/{name}` and its export the same with `/export`; the page's
 * connection, forms and confirmations still come from `GET /api/v1/connectors`
 * (`pages/connectorsQuery.ts`). The writes are connect and disconnect (as before), edit,
 * replacing a key, and naming the source's steward (M7.7.2).
 *
 * **A reader keeps only what was sent.** Every field is read back through a check of its type, and
 * a field the API did not send is absent from the row rather than defaulted, so a cell for a source
 * the reader may not be told is connected is empty, never "unknown", which would say something was
 * withheld. See `brain.console.connector_detail.A_SOURCE_NOBODY_CONNECTED_AND_ONE_YOU_MAY_NOT_SEE_READ_ALIKE`.
 *
 * **No key and no vault path is read out of any answer here**, because none is sent; the reader has
 * no field that could hold one, so a key added to a response by mistake is dropped at this line.
 *
 * Task ids: M27.11.9, M27.15.39, M27.15.58, M27.16.1, M7.7.2
 */

/** The module's list, one source's page and its export, under the API base. */
export const SOURCES_API_PATH = "/console/connectors";

export function sourceApiPath(name: string): string {
  return `${SOURCES_API_PATH}/${encodeURIComponent(name)}`;
}

export function exportApiPath(name: string): string {
  return `${sourceApiPath(name)}/export`;
}

/** Where a connected source's settings are edited, and its key replaced. */
export function editApiPath(name: string): string {
  return `/connectors/${encodeURIComponent(name)}/edit`;
}

export function keyApiPath(name: string): string {
  return `/connectors/${encodeURIComponent(name)}/key`;
}

/** Where a connected source's steward is named (M7.7.2). */
export function stewardApiPath(name: string): string {
  return `/connectors/${encodeURIComponent(name)}/steward`;
}

/** The module's own address, which is the screen's key in `brain.console.screens`. */
export const CONNECTORS_ADDRESS = "/connectors";

/** Where one source's page is. The Dashboard is the bare address. */
export function connectorAddress(name: string): string {
  return `${CONNECTORS_ADDRESS}/${encodeURIComponent(name)}`;
}

/** A status word as a person reads it. Closed on the API side; there is no fourth. */
export const STATUS_WORDS: Readonly<Record<string, string>> = Object.freeze({
  connected: "Connected",
  not_connected: "Not connected",
  failing: "Failing",
});

/** The worker's health word as a person reads it. */
export const HEALTH_WORDS: Readonly<Record<string, string>> = Object.freeze({
  ok: "Healthy",
  degraded: "Degraded",
  down: "Down",
  unconfigured: "Not set up",
});

/** Where a source is connected, as a person reads it. */
export const CONNECT_FROM_WORDS: Readonly<Record<string, string>> = Object.freeze({
  console: "Connected from this screen",
  lark: "Connected through Connect Lark",
  server: "Connected at the server",
});

export function statusWords(status: string): string {
  return STATUS_WORDS[status] ?? status;
}

export function healthWords(health: string): string {
  return HEALTH_WORDS[health] ?? health;
}

// ------------------------------------------------------------------------ reading a body

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `instant` or `listOf` below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function instant(value: unknown): string | undefined {
  const text = said(value);
  return text !== undefined && !Number.isNaN(Date.parse(text)) ? text : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function words(value: unknown): readonly string[] {
  return listOf(value).filter((one): one is string => typeof one === "string" && one !== "");
}

/** One source on the list, as `brain.connector_routes.SourceRowView` sends it. */
export interface SourceRow {
  readonly name: string;
  readonly label: string;
  readonly status: string;
  readonly health?: string;
  readonly department?: string;
  readonly lastReadAt?: string;
  readonly connectedAt?: string;
  readonly declarationChanged: boolean;
  readonly connectFrom: string;
  readonly mayManage: boolean;
}

export function readSourceRow(value: unknown): SourceRow | null {
  const fields = fieldsOf(value);
  const name = said(fields?.["name"]);
  const label = said(fields?.["label"]);
  const status = said(fields?.["status"]);
  const connectFrom = said(fields?.["connect_from"]);
  if (fields === null || name === undefined || label === undefined || status === undefined || connectFrom === undefined) {
    return null;
  }
  const health = said(fields["health"]);
  const department = said(fields["department"]);
  const lastReadAt = instant(fields["last_read_at"]);
  const connectedAt = instant(fields["connected_at"]);
  return {
    name,
    label,
    status,
    ...(health === undefined ? {} : { health }),
    ...(department === undefined ? {} : { department }),
    ...(lastReadAt === undefined ? {} : { lastReadAt }),
    ...(connectedAt === undefined ? {} : { connectedAt }),
    declarationChanged: fields["declaration_changed"] === true,
    connectFrom,
    mayManage: fields["may_manage"] === true,
  };
}

/** The rows out of the list's body, each once, in the order they came. */
export function readSourceRows(payload: unknown): readonly SourceRow[] {
  const seen = new Set<string>();
  const rows: SourceRow[] = [];
  for (const item of listOf(fieldsOf(payload)?.["items"])) {
    const row = readSourceRow(item);
    if (row !== null && !seen.has(row.name)) {
      seen.add(row.name);
      rows.push(row);
    }
  }
  return rows;
}

/** One identifier a connection was made with, under the label its form asks for it by. */
export interface SettingValue {
  readonly name: string;
  readonly label: string;
  readonly value: string;
}

export interface KeptEntity {
  readonly entity: string;
  readonly fields: readonly string[];
}

export interface LiveRead {
  readonly tool: string;
  readonly entity: string;
  readonly description: string;
}

export interface HistoryEntry {
  readonly connectedAt: string;
  readonly connectedBy: string;
  readonly disconnectedAt?: string;
  readonly disconnectedBy?: string;
  readonly settings: readonly SettingValue[];
}

export interface NamedAgent {
  readonly agentId: string;
  readonly displayName: string;
}

export interface NamedSkill {
  readonly name: string;
  readonly version: string;
  readonly state: string;
}

/** One source whole, as `brain.connector_routes.SourceView` sends it. */
export interface SourceDetail {
  readonly source: SourceRow;
  readonly elsewhere?: string;
  readonly reading?: string;
  readonly ceiling?: string;
  readonly recorded?: string;
  readonly departmentSays?: string;
  readonly settings: readonly SettingValue[];
  readonly keeps: readonly KeptEntity[];
  readonly readsLive: readonly LiveRead[];
  readonly history: readonly HistoryEntry[];
  readonly people: Readonly<Record<string, string>>;
  readonly agents: readonly NamedAgent[];
  readonly skills: readonly NamedSkill[];
  readonly confirmEdit: string;
  readonly confirmKey: string;
  /** Who answers for the source, by principal id, when it is connected and the reader may be told. */
  readonly steward?: string;
  /** The API's sentence for what naming a steward agrees to. */
  readonly confirmSteward: string;
}

function readSettings(value: unknown): readonly SettingValue[] {
  const found: SettingValue[] = [];
  for (const one of listOf(value)) {
    const fields = fieldsOf(one);
    const name = said(fields?.["name"]);
    const label = said(fields?.["label"]);
    const typed = typeof fields?.["value"] === "string" ? (fields["value"] as string) : undefined;
    if (name !== undefined && label !== undefined && typed !== undefined) {
      found.push({ name, label, value: typed });
    }
  }
  return found;
}

function readHistory(value: unknown): readonly HistoryEntry[] {
  const found: HistoryEntry[] = [];
  for (const one of listOf(value)) {
    const fields = fieldsOf(one);
    const connectedAt = instant(fields?.["connected_at"]);
    const connectedBy = said(fields?.["connected_by"]);
    if (fields === null || connectedAt === undefined || connectedBy === undefined) {
      continue;
    }
    const disconnectedAt = instant(fields["disconnected_at"]);
    const disconnectedBy = said(fields["disconnected_by"]);
    found.push({
      connectedAt,
      connectedBy,
      ...(disconnectedAt === undefined ? {} : { disconnectedAt }),
      ...(disconnectedBy === undefined ? {} : { disconnectedBy }),
      settings: readSettings(fields["settings"]),
    });
  }
  return found;
}

function readPeople(value: unknown): Readonly<Record<string, string>> {
  const fields = fieldsOf(value);
  if (fields === null) {
    return {};
  }
  const found: Record<string, string> = {};
  for (const [id, name] of Object.entries(fields)) {
    const named = said(name);
    if (named !== undefined) {
      found[id] = named;
    }
  }
  return found;
}

/** One source's page out of its body, or null when the body is not one. */
export function readSourceDetail(payload: unknown): SourceDetail | null {
  const fields = fieldsOf(payload);
  const source = readSourceRow(fields?.["source"]);
  if (fields === null || source === null) {
    return null;
  }
  const keeps: KeptEntity[] = [];
  for (const one of listOf(fields["keeps"])) {
    const entity = said(fieldsOf(one)?.["entity"]);
    if (entity !== undefined) {
      keeps.push({ entity, fields: words(fieldsOf(one)?.["fields"]) });
    }
  }
  const readsLive: LiveRead[] = [];
  for (const one of listOf(fields["reads_live"])) {
    const row = fieldsOf(one);
    const tool = said(row?.["tool"]);
    if (tool !== undefined) {
      readsLive.push({ tool, entity: said(row?.["entity"]) ?? "", description: said(row?.["description"]) ?? "" });
    }
  }
  const agents: NamedAgent[] = [];
  for (const one of listOf(fields["agents"])) {
    const agentId = said(fieldsOf(one)?.["agent_id"]);
    const displayName = said(fieldsOf(one)?.["display_name"]);
    if (agentId !== undefined && displayName !== undefined) {
      agents.push({ agentId, displayName });
    }
  }
  const skills: NamedSkill[] = [];
  for (const one of listOf(fields["skills"])) {
    const name = said(fieldsOf(one)?.["name"]);
    if (name !== undefined) {
      skills.push({ name, version: said(fieldsOf(one)?.["version"]) ?? "", state: said(fieldsOf(one)?.["state"]) ?? "" });
    }
  }
  const elsewhere = said(fields["elsewhere"]);
  const reading = said(fields["reading"]);
  const ceiling = said(fields["ceiling"]);
  const recorded = said(fields["recorded"]);
  const departmentSays = said(fields["department_says"]);
  const steward = said(fields["steward"]);
  return {
    source,
    ...(elsewhere === undefined ? {} : { elsewhere }),
    ...(reading === undefined ? {} : { reading }),
    ...(ceiling === undefined ? {} : { ceiling }),
    ...(recorded === undefined ? {} : { recorded }),
    ...(departmentSays === undefined ? {} : { departmentSays }),
    settings: readSettings(fields["settings"]),
    keeps,
    readsLive,
    history: readHistory(fields["history"]),
    people: readPeople(fields["people"]),
    agents,
    skills,
    confirmEdit: said(fields["confirm_edit"]) ?? "",
    confirmKey: said(fields["confirm_key"]) ?? "",
    ...(steward === undefined ? {} : { steward }),
    confirmSteward: said(fields["confirm_steward"]) ?? "",
  };
}

/** A person as a page names them: their display name, or a sentence when none is known. */
export function personWords(people: Readonly<Record<string, string>>, id: string | undefined): string {
  if (id === undefined) {
    return "";
  }
  return people[id] ?? "a person no longer listed";
}

/** An instant as a date and a time, in the reader's own time zone. */
export function dateWords(at: string | undefined): string | undefined {
  if (at === undefined) {
    return undefined;
  }
  return new Date(at).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** The filename an export is saved under. The source's own name, which is a slug. */
export function exportFileName(name: string): string {
  return `connector-${name}.json`;
}
