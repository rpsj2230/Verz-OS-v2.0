/**
 * What one agent is built from, in the detail its Profile draws: `brain.agent_capability_routes`.
 *
 * **Read as sent, and absent as absent.** A connector's health, a skill's version and review, and
 * the knowledge slice are each carried only when the body gave them in the declared shape, so a
 * reader the API told nothing about the library sees chips with no review pill rather than pills
 * reading "unknown". Nothing here is a count of anything hidden: the route sends none, and this file
 * derives none.
 *
 * **The acts are the Skills page's own routes.** Attaching an approved skill is `POST
 * /skills/{digest}/assignments` and taking one off is `POST /skills/{digest}/detachments`, each
 * with the agent in the body; the page asks the capabilities again after either, so the chips are
 * what the install now holds.
 *
 * Task ids: M39.2.1.1, M39.2.1.3, M39.2.1.5, M39.2.2.1, M39.2.2.2, M39.2.2.3, M39.2.2.4
 * Task ids: M39.2.3.1, M39.2.3.3, M39.2.3.4, M39.3.1.1, M39.3.1.3, M39.3.1.4
 */

/** Where one agent's capability detail is asked for, under the API base. */
export function agentCapabilitiesApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/capabilities`;
}

/** Where one person's run of one agent is previewed, under the API base. */
export function agentPreviewApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/preview`;
}

/** Where a library skill is attached to an agent, under the API base. */
export function skillAssignApiPath(digest: string): string {
  return `/skills/${encodeURIComponent(digest)}/assignments`;
}

/** Where a skill is taken off an agent, under the API base. */
export function skillDetachApiPath(digest: string): string {
  return `/skills/${encodeURIComponent(digest)}/detachments`;
}

export interface Availability {
  readonly level: string;
  readonly department?: string;
  readonly ownerId: string;
  readonly readerIsIncluded: boolean;
  readonly words: string;
}

export interface ConnectorDetail {
  readonly source: string;
  readonly presence: string;
  readonly projects: readonly string[];
  readonly health?: string;
  readonly checkedAt?: string;
}

export interface SkillChip {
  readonly name: string;
  readonly digest: string;
  readonly version?: string;
  readonly source?: string;
  readonly review?: string;
  readonly runs: number;
  readonly detachable: boolean;
}

export interface SkillOffer {
  readonly name: string;
  readonly version: string;
  readonly digest: string;
  readonly review: string;
  /** `attach`, `review` or `nothing`: `brain.console.agent_tabs.Control`. */
  readonly control: string;
  readonly route: string;
}

export interface Clause {
  readonly field: string;
  readonly op: string;
  readonly value: string;
}

export interface KnowledgeSlice {
  readonly clauses: readonly Clause[];
  readonly matched: number;
  readonly verified: number;
  readonly stale: number;
  readonly unverified: number;
  readonly atLeast: boolean;
}

export interface AgentCapabilities {
  readonly availability?: Availability;
  readonly connectors: readonly ConnectorDetail[];
  readonly skills: readonly SkillChip[];
  readonly unusedSkills: readonly string[];
  readonly usageBasis?: string;
  readonly skillsEditable: boolean;
  readonly offers: readonly SkillOffer[];
  readonly knowledge?: KnowledgeSlice;
}

export interface PreviewTool {
  readonly name: string;
  readonly description?: string;
}

export interface Preview {
  readonly personId: string;
  readonly personName?: string;
  readonly tools: readonly PreviewTool[];
  readonly rung?: string;
  readonly notice?: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `counted` or an exact comparison below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function counted(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function words(value: unknown): readonly string[] {
  return listOf(value)
    .map(said)
    .filter((one): one is string => one !== undefined);
}

function readAvailability(value: unknown): Availability | undefined {
  const fields = fieldsOf(value);
  const level = said(fields?.["level"]);
  const ownerId = said(fields?.["owner_id"]);
  const sentence = said(fields?.["words"]);
  if (fields === null || level === undefined || ownerId === undefined || sentence === undefined) {
    return undefined;
  }
  const department = said(fields["department"]);
  return {
    level,
    ownerId,
    words: sentence,
    readerIsIncluded: fields["reader_is_included"] === true,
    ...(department === undefined ? {} : { department }),
  };
}

function readConnector(value: unknown): ConnectorDetail | null {
  const fields = fieldsOf(value);
  const source = said(fields?.["source"]);
  const presence = said(fields?.["presence"]);
  if (fields === null || source === undefined || presence === undefined) {
    return null;
  }
  const health = said(fields["health"]);
  const checked = said(fields["checked_at"]);
  const checkedAt = checked !== undefined && !Number.isNaN(Date.parse(checked)) ? checked : undefined;
  return {
    source,
    presence,
    projects: words(fields["projects"]),
    // Health and its instant travel together or not at all, as the route sends them.
    ...(health === undefined || checkedAt === undefined ? {} : { health, checkedAt }),
  };
}

function readChip(value: unknown): SkillChip | null {
  const fields = fieldsOf(value);
  const name = said(fields?.["name"]);
  const digest = said(fields?.["digest"]);
  const runs = counted(fields?.["runs"]);
  if (fields === null || name === undefined || digest === undefined || runs === undefined) {
    return null;
  }
  const version = said(fields["version"]);
  const source = said(fields["source"]);
  const review = said(fields["review"]);
  return {
    name,
    digest,
    runs,
    detachable: fields["detachable"] === true,
    ...(version === undefined ? {} : { version }),
    ...(source === undefined ? {} : { source }),
    ...(review === undefined ? {} : { review }),
  };
}

function readOffer(value: unknown): SkillOffer | null {
  const fields = fieldsOf(value);
  const name = said(fields?.["name"]);
  const version = said(fields?.["version"]);
  const digest = said(fields?.["digest"]);
  const review = said(fields?.["review"]);
  const control = said(fields?.["control"]);
  if (fields === null || name === undefined || version === undefined || digest === undefined || review === undefined || control === undefined) {
    return null;
  }
  return { name, version, digest, review, control, route: said(fields["route"]) ?? "" };
}

function readKnowledge(value: unknown): KnowledgeSlice | undefined {
  const fields = fieldsOf(value);
  const matched = counted(fields?.["matched"]);
  const verified = counted(fields?.["verified"]);
  const stale = counted(fields?.["stale"]);
  const unverified = counted(fields?.["unverified"]);
  if (fields === null || matched === undefined || verified === undefined || stale === undefined || unverified === undefined) {
    return undefined;
  }
  const clauses: Clause[] = [];
  for (const one of listOf(fields["clauses"])) {
    const clause = fieldsOf(one);
    const field = said(clause?.["field"]);
    const op = said(clause?.["op"]);
    const value = said(clause?.["value"]);
    if (field !== undefined && op !== undefined && value !== undefined) {
      clauses.push({ field, op, value });
    }
  }
  return { clauses, matched, verified, stale, unverified, atLeast: fields["at_least"] === true };
}

function each<T>(value: unknown, read: (one: unknown) => T | null): T[] {
  return listOf(value)
    .map(read)
    .filter((one): one is T => one !== null);
}

/** The capability detail out of a body, or null when the body is not an object at all. */
export function readAgentCapabilities(payload: unknown): AgentCapabilities | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const availability = readAvailability(fields["availability"]);
  const knowledge = readKnowledge(fields["knowledge"]);
  const usageBasis = said(fields["usage_basis"]);
  return {
    connectors: each(fields["connectors"], readConnector),
    skills: each(fields["skills"], readChip),
    unusedSkills: words(fields["unused_skills"]),
    skillsEditable: fields["skills_editable"] === true,
    offers: each(fields["offers"], readOffer),
    ...(availability === undefined ? {} : { availability }),
    ...(knowledge === undefined ? {} : { knowledge }),
    ...(usageBasis === undefined ? {} : { usageBasis }),
  };
}

/** A preview out of a body, or null when it is not one. */
export function readPreview(payload: unknown): Preview | null {
  const fields = fieldsOf(payload);
  const personId = said(fields?.["person_id"]);
  if (fields === null || personId === undefined) {
    return null;
  }
  const personName = said(fields["person_name"]);
  const rung = said(fields["rung"]);
  const notice = said(fields["notice"]);
  const tools: PreviewTool[] = [];
  for (const one of listOf(fields["tools"])) {
    const tool = fieldsOf(one);
    const name = said(tool?.["name"]);
    const description = said(tool?.["description"]);
    if (name !== undefined) {
      tools.push({ name, ...(description === undefined ? {} : { description }) });
    }
  }
  return {
    personId,
    tools,
    ...(personName === undefined ? {} : { personName }),
    ...(rung === undefined ? {} : { rung }),
    ...(notice === undefined ? {} : { notice }),
  };
}

/** Where a skill came from, as a person reads it: `brain.tools.skills.SourceKind`'s three words. */
export const SOURCE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  github: "from GitHub",
  url: "from an address",
  upload: "uploaded",
});

/** A predicate clause as a person reads it. */
export function clauseWords(clause: Clause): string {
  const value = clause.value;
  switch (clause.field) {
    case "department":
      return `documents in the ${value} department`;
    case "owner_id":
      return `documents stewarded by ${value}`;
    case "visibility":
      return `documents visible at the ${value} level`;
    case "state":
      return `documents that are ${value}`;
    default:
      return `${clause.field} ${clause.op} ${value}`;
  }
}
