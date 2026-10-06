/**
 * The grants people gave themselves that reach what the reader stewards (M7.7.2), below the
 * requests on the Access requests page, because both are the reader being told about access to what
 * they answer for.
 *
 * **The list is the reader's own and the API decides every row.** `GET /stewardship/self-grants`
 * answers for the caller alone: which grants reach which of their documents, sources and agents is
 * `brain.identity.stewardship.notices_for`, and nothing here filters, counts or adds to it. An empty
 * list is one sentence, the same whether nobody granted themselves anything or the reader stewards
 * nothing, so the page says nothing about anybody else's things.
 *
 * **Each row names the person, when, what they granted themselves, and the reader's things it
 * reaches**, each linked to its own page. Never the grant's scope, which the API does not send.
 *
 * **Nothing here changes anything.** Removing a grant is done on the People screen, which the API's
 * sentence above the list says.
 *
 * Task ids: M7.7.2
 */

import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { AGENT_ADDRESS_PREFIX } from "../../components/agentWorkspaceState";
import { Chip, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { connectorAddress } from "../connectors/connectorSources";
import { documentAddress } from "../knowledge/knowledgeDocuments";
import { whenWords } from "../review/parts";

export const SELF_GRANTS_API_PATH = "/stewardship/self-grants";
export const SELF_GRANTS_HEADING = "Access people gave themselves";
export const NO_SELF_GRANTS = "Nobody has given themselves access to anything you steward.";
export const READING_SELF_GRANTS = "Reading the access people gave themselves.";

/** What kind of thing a row reaches, as a person reads it. */
export const KIND_WORDS: Readonly<Record<string, string>> = Object.freeze({
  document: "Document",
  source: "Source",
  agent: "Agent",
});

export interface Reached {
  readonly kind: string;
  readonly objectId: string;
  readonly label: string;
}

export interface SelfGrantNotice {
  readonly at: string;
  readonly personId: string;
  readonly personName: string;
  readonly pack: string;
  readonly capabilities: readonly string[];
  readonly reached: readonly Reached[];
}

export interface SelfGrantNotices {
  readonly items: readonly SelfGrantNotice[];
  readonly told: string;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function fields(value: unknown): Readonly<Record<string, unknown>> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function list(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : [];
}

/** The API's answer, keeping only rows that name a person, a time and something reached. */
export function readSelfGrants(payload: unknown): SelfGrantNotices {
  const body = fields(payload);
  const items: SelfGrantNotice[] = [];
  for (const one of list(body?.["items"])) {
    const row = fields(one);
    const reached: Reached[] = [];
    for (const thing of list(row?.["reached"])) {
      const shown = fields(thing);
      const objectId = text(shown?.["object_id"]);
      if (objectId !== "") {
        reached.push({ kind: text(shown?.["kind"]), objectId, label: text(shown?.["label"]) || objectId });
      }
    }
    const personId = text(row?.["person_id"]);
    const at = text(row?.["at"]);
    if (personId === "" || at === "" || reached.length === 0) {
      continue;
    }
    items.push({
      at,
      personId,
      personName: text(row?.["person_name"]),
      pack: text(row?.["pack"]),
      capabilities: list(row?.["capabilities"]).filter((cap): cap is string => typeof cap === "string"),
      reached,
    });
  }
  return { items, told: text(body?.["told"]) };
}

/** Where a reached thing's own page is. */
export function reachedAddress(thing: Reached): string | null {
  if (thing.kind === "document") {
    return documentAddress(thing.objectId);
  }
  if (thing.kind === "source") {
    return connectorAddress(thing.objectId);
  }
  if (thing.kind === "agent") {
    return `${AGENT_ADDRESS_PREFIX}${encodeURIComponent(thing.objectId)}`;
  }
  return null;
}

function ReachedLink({ thing }: { readonly thing: Reached }) {
  const to = reachedAddress(thing);
  const words = `${KIND_WORDS[thing.kind] ?? thing.kind}: ${thing.label}`;
  return to === null ? (
    <span>{words}</span>
  ) : (
    <Link to={to} className="text-acc-text underline-offset-4 hover:underline">
      {words}
    </Link>
  );
}

export function SelfGrantNoticesSection() {
  const answer = useResource<unknown>(SELF_GRANTS_API_PATH);
  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.busy) {
    body = <LoadingState label={READING_SELF_GRANTS} />;
  } else {
    const found = readSelfGrants(answer.data);
    body =
      found.items.length === 0 ? (
        <p className="m-0 text-dim">{NO_SELF_GRANTS}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-3 p-0" aria-label={SELF_GRANTS_HEADING}>
          {found.items.map((one) => (
            <li key={`${one.personId}-${one.at}`} className="flex min-w-0 flex-col gap-1 border-b border-line pb-3 last:border-b-0">
              <span className="[overflow-wrap:anywhere]">
                <span className="font-medium text-ink">{one.personName || one.personId}</span> gave themselves{" "}
                {one.pack === "" ? "access" : `the ${one.pack} pack`} on {whenWords(one.at)}
              </span>
              <span className="flex flex-wrap gap-1">
                {one.capabilities.map((cap) => (
                  <Chip key={cap} mono>
                    {cap}
                  </Chip>
                ))}
              </span>
              <span className="flex flex-wrap gap-x-3 gap-y-1 text-[13px]">
                {one.reached.map((thing) => (
                  <ReachedLink key={`${thing.kind}-${thing.objectId}`} thing={thing} />
                ))}
              </span>
            </li>
          ))}
        </ul>
      );
  }
  const told = answer.data === null ? "" : readSelfGrants(answer.data).told;
  return (
    <SectionCard title={SELF_GRANTS_HEADING} lede={told === "" ? undefined : <Note>{told}</Note>}>
      {body}
    </SectionCard>
  );
}
