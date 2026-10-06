/**
 * One agent's artifacts, as `brain.agent_artifact_routes` sends them, the addresses of their file and
 * their two changes, and the query a filter becomes. No React.
 *
 * **Read as sent, and absent as absent.** An artifact missing its id, kind or date is left out rather
 * than drawn blank; the summary missing is no figures, never noughts; `unread` is the one sentence a
 * process with no record of artifacts answers with. Nothing here counts anything.
 *
 * **A filter is a query the API answers, never a pass over what it sent.** The list the reader sees
 * is `visible_artifacts`'s answer to the filter, which is that function's own argument: a filter run
 * in the browser over a list would have to be handed the unfiltered list first.
 *
 * Task ids: M39.5.2.1, M39.5.2.2, M39.5.2.3, M39.5.2.4, M39.5.2.5, M39.5.1.5
 */

/** Where one agent's artifacts are asked for, under the API base, with any filter as a query. */
export function agentArtifactsApiPath(agentId: string, filter: ArtifactFilter = NO_FILTER): string {
  const query = new URLSearchParams();
  if (filter.kind !== "") {
    query.set("kind", filter.kind);
  }
  if (filter.producedFor !== "") {
    query.set("produced_for", filter.producedFor);
  }
  if (filter.from !== "") {
    query.set("since", `${filter.from}T00:00:00Z`);
  }
  if (filter.to !== "") {
    query.set("until", `${filter.to}T23:59:59Z`);
  }
  const said = query.toString();
  return `/agents/${encodeURIComponent(agentId)}/artifacts${said === "" ? "" : `?${said}`}`;
}

/** Where one artifact's file is fetched, under the API base. */
export function artifactFileApiPath(agentId: string, artifactId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/artifacts/${encodeURIComponent(artifactId)}/download`;
}

/** Where one artifact is archived, under the API base. */
export function artifactArchiveApiPath(agentId: string, artifactId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/artifacts/${encodeURIComponent(artifactId)}/archive`;
}

/** Where one artifact is marked replaced by another, under the API base. */
export function artifactSupersedeApiPath(agentId: string, artifactId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/artifacts/${encodeURIComponent(artifactId)}/supersede`;
}

/** What the reader chose to narrow the list by. Empty means not narrowed. */
export interface ArtifactFilter {
  readonly kind: string;
  readonly producedFor: string;
  /** Whole days, `YYYY-MM-DD`, as a date input gives them. */
  readonly from: string;
  readonly to: string;
}

export const NO_FILTER: ArtifactFilter = Object.freeze({ kind: "", producedFor: "", from: "", to: "" });

export interface KnowledgeRef {
  readonly itemId: string;
  readonly title: string;
}

export interface ArtifactItem {
  readonly artifactId: string;
  readonly kind: string;
  readonly producedFor: string;
  readonly producedForName: string;
  readonly producedAt: string;
  readonly state: string;
  readonly supersededBy: string;
  readonly runId: string;
  readonly agentVersion: string;
  readonly keptAs: string;
  readonly keptUntil?: string;
  readonly keptBecause: string;
  readonly bytesStored: number;
  readonly clientId: string;
  readonly sources: readonly string[];
  readonly knowledge: readonly KnowledgeRef[];
  readonly downloadable: boolean;
  readonly changeable: boolean;
}

export interface ArtifactPerson {
  readonly principalId: string;
  readonly name: string;
}

export interface ArtifactSummary {
  readonly basis: string;
  readonly count: number;
  readonly bytesStored: number;
  readonly oldestAt?: string;
  readonly expiresSoonestAt?: string;
}

export interface AgentArtifacts {
  readonly artifacts: readonly ArtifactItem[];
  readonly summary?: ArtifactSummary;
  readonly kinds: readonly string[];
  readonly people: readonly ArtifactPerson[];
  readonly keptRule: string;
  /** Set when nothing on this process records artifacts, with an empty list. */
  readonly unread?: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `listOf` or a type test below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function each<T>(value: unknown, read: (one: Fields) => T | null): T[] {
  return listOf(value)
    .map(fieldsOf)
    .map((one) => (one === null ? null : read(one)))
    .filter((one): one is T => one !== null);
}

function readItem(one: Fields): ArtifactItem | null {
  const artifactId = said(one["artifact_id"]);
  const kind = said(one["kind"]);
  const producedAt = said(one["produced_at"]);
  const producedFor = said(one["produced_for"]);
  if (artifactId === undefined || kind === undefined || producedAt === undefined || producedFor === undefined) {
    return null;
  }
  const provenance = fieldsOf(one["provenance"]);
  const keptUntil = said(one["kept_until"]);
  const bytes = one["bytes_stored"];
  return {
    artifactId,
    kind,
    producedAt,
    producedFor,
    producedForName: said(one["produced_for_name"]) ?? "",
    state: said(one["state"]) ?? "current",
    supersededBy: said(one["superseded_by"]) ?? "",
    runId: said(one["run_id"]) ?? "",
    agentVersion: said(one["agent_version"]) ?? "",
    keptAs: said(one["kept_as"]) ?? "",
    ...(keptUntil === undefined ? {} : { keptUntil }),
    keptBecause: said(one["kept_because"]) ?? "",
    bytesStored: typeof bytes === "number" ? bytes : 0,
    clientId: said(one["client_id"]) ?? "",
    sources: listOf(provenance?.["sources"]).filter((name): name is string => typeof name === "string"),
    knowledge: each(provenance?.["knowledge_items"], (ref) => {
      const itemId = said(ref["item_id"]);
      const title = said(ref["title"]);
      return itemId === undefined || title === undefined ? null : { itemId, title };
    }),
    downloadable: one["downloadable"] === true,
    changeable: one["changeable"] === true,
  };
}

function readSummary(value: unknown): ArtifactSummary | undefined {
  const one = fieldsOf(value);
  if (one === null || typeof one["count"] !== "number" || typeof one["bytes_stored"] !== "number") {
    return undefined;
  }
  const oldestAt = said(one["oldest_at"]);
  const expiresSoonestAt = said(one["expires_soonest_at"]);
  return {
    basis: said(one["basis"]) ?? "",
    count: one["count"],
    bytesStored: one["bytes_stored"],
    ...(oldestAt === undefined ? {} : { oldestAt }),
    ...(expiresSoonestAt === undefined ? {} : { expiresSoonestAt }),
  };
}

/** The Artifacts section out of a body, or null when the body is not an object at all. */
export function readAgentArtifacts(payload: unknown): AgentArtifacts | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const summary = readSummary(fields["summary"]);
  const unread = said(fields["unread"]);
  return {
    artifacts: each(fields["artifacts"], readItem),
    ...(summary === undefined ? {} : { summary }),
    kinds: listOf(fields["kinds"]).filter((one): one is string => typeof one === "string"),
    people: each(fields["people"], (one) => {
      const principalId = said(one["principal_id"]);
      return principalId === undefined ? null : { principalId, name: said(one["name"]) ?? principalId };
    }),
    keptRule: said(fields["kept_rule"]) ?? "",
    ...(unread === undefined ? {} : { unread }),
  };
}

/** Each kind of artifact, in words: `brain.console.agent_output.ArtifactKind`'s five. */
export const KIND_WORDS: Readonly<Record<string, string>> = Object.freeze({
  document: "Document",
  deck: "Deck",
  report: "Report",
  export: "Export",
  image: "Image",
});

/** Where an artifact is in its life, in words: `ArtifactState`'s three. */
export const STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  current: "Current",
  superseded: "Replaced by a newer version",
  archived: "Archived",
});

/** A size in bytes as a person reads it. */
export function sizeWords(bytes: number): string {
  if (bytes < 1024) {
    return `${String(bytes)} bytes`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** What a saved file is called: its kind and its id, never a title. */
export function fileName(item: ArtifactItem, type: string): string {
  const extension = type.startsWith("text/csv") ? "csv" : type.startsWith("application/pdf") ? "pdf" : "bin";
  return `${item.kind}-${item.artifactId}.${extension}`;
}
