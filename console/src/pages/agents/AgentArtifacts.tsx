/**
 * An agent's Artifacts section: what it produced for people, filtered by type, person and date, with
 * what fed each one, how long each is kept, and the file itself for whoever may fetch it now.
 *
 * **Every row is the route's, drawn as sent.** The list is `visible_artifacts`'s answer to the
 * filter the reader chose, so a filter is a new request and never a pass over a list the browser
 * already holds. An empty list says so in one sentence that claims nothing about what anybody else
 * may see, and the count beside it is a count of what is shown.
 *
 * **The file is offered only where the API said this reader may fetch it**, and fetching it asks the
 * API again: a download is re-checked at the requester's reach when it is pressed, and a refusal is
 * the API's own sentence. The file is handed to the browser and kept nowhere on the page.
 *
 * **Superseding and archiving are confirmed, and offered only where the API said so.** Neither
 * removes anything: the artifact stays listed with what happened to it, which the dialog says before
 * anything is sent.
 *
 * Task ids: M39.5.2.1, M39.5.2.2, M39.5.2.3, M39.5.2.4, M39.5.2.5, M39.5.1.5
 */

import { Download, FileText } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { request, requestFile } from "../../api/client";
import { useResource } from "../../api/useResource";
import { basisWords } from "../../components/AgentAssembly";
import { Chip, ConfirmDialog, FailureState, KpiStrip, LoadingState, Note, SectionCard, StatCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { dayWords } from "../access/formParts";
import {
  KIND_WORDS,
  NO_FILTER,
  STATE_WORDS,
  agentArtifactsApiPath,
  artifactArchiveApiPath,
  artifactFileApiPath,
  artifactSupersedeApiPath,
  fileName,
  readAgentArtifacts,
  sizeWords,
  type AgentArtifacts as Artifacts,
  type ArtifactFilter,
  type ArtifactItem,
} from "./agentArtifactsQuery";

export const ARTIFACTS_HEADING = "What it produced";
export const ARTIFACTS_FIGURES = "What you may see of what it produced";
export const NOTHING_PRODUCED = "Nothing this agent produced is yours to see yet.";
export const NOTHING_MATCHES = "Nothing you may see matches this filter.";
export const LOADING_ARTIFACTS = "Loading what this agent produced.";
export const CANNOT_SAVE_FILE = "This browser could not save the file. Nothing about the artifact has changed.";
export const EVERY_KIND = "Every type";
export const EVERYBODY = "Everybody";

type Asking =
  | { readonly kind: "archive"; readonly item: ArtifactItem }
  | { readonly kind: "supersede"; readonly item: ArtifactItem };

const CONTROL = "h-9 min-w-0 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink";

/** What the filter offers: the five kinds and the people the reader already sees. */
interface Choices {
  readonly kinds: Artifacts["kinds"];
  readonly people: Artifacts["people"];
}

function Filters({
  artifacts,
  filter,
  onFilter,
}: {
  readonly artifacts: Choices;
  readonly filter: ArtifactFilter;
  readonly onFilter: (next: ArtifactFilter) => void;
}) {
  const id = useId();
  return (
    <div data-slot="artifact-filters" role="group" aria-label="Filter what it produced" className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${id}-kind`}>Type</Label>
        <select id={`${id}-kind`} className={CONTROL} value={filter.kind} onChange={(event) => onFilter({ ...filter, kind: event.target.value })}>
          <option value="">{EVERY_KIND}</option>
          {artifacts.kinds.map((one) => (
            <option key={one} value={one}>
              {KIND_WORDS[one] ?? one}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${id}-for`}>Produced for</Label>
        <select id={`${id}-for`} className={CONTROL} value={filter.producedFor} onChange={(event) => onFilter({ ...filter, producedFor: event.target.value })}>
          <option value="">{EVERYBODY}</option>
          {artifacts.people.map((one) => (
            <option key={one.principalId} value={one.principalId}>
              {one.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${id}-from`}>From</Label>
        <input id={`${id}-from`} type="date" className={CONTROL} value={filter.from} onChange={(event) => onFilter({ ...filter, from: event.target.value })} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${id}-to`}>To</Label>
        <input id={`${id}-to`} type="date" className={CONTROL} value={filter.to} onChange={(event) => onFilter({ ...filter, to: event.target.value })} />
      </div>
      {filter === NO_FILTER ? null : (
        <Button variant="ghost" size="sm" className="min-h-11 sm:min-h-8" onClick={() => onFilter(NO_FILTER)}>
          Clear filters
        </Button>
      )}
    </div>
  );
}

function Figures({ artifacts }: { readonly artifacts: Artifacts }) {
  const summary = artifacts.summary;
  if (summary === undefined) {
    return null;
  }
  return (
    <KpiStrip label={ARTIFACTS_FIGURES} count={3}>
      <StatCard label="Artifacts" value={String(summary.count)} sub={basisWords(summary.basis)} />
      <StatCard label="Storage" value={sizeWords(summary.bytesStored)} sub={summary.oldestAt === undefined ? undefined : `oldest ${dayWords(summary.oldestAt)}`} />
      <StatCard
        label="Next one goes"
        value={summary.expiresSoonestAt === undefined ? "No date" : dayWords(summary.expiresSoonestAt)}
        sub={summary.expiresSoonestAt === undefined ? "none of them is kept by age" : "when its window closes"}
      />
    </KpiStrip>
  );
}

function ArtifactRow({
  item,
  onAsk,
  onFetch,
  canSupersede,
}: {
  readonly item: ArtifactItem;
  readonly onAsk: (asking: Asking) => void;
  readonly onFetch: (item: ArtifactItem) => void;
  readonly canSupersede: boolean;
}) {
  return (
    <li data-slot="artifact-item" className="flex flex-col gap-1.5 border-b border-line py-2.5 text-[13px] last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        <FileText aria-hidden className="size-4 text-dim" />
        <span className="font-medium text-ink">{KIND_WORDS[item.kind] ?? item.kind}</span>
        <span className="text-dim">{`for ${item.producedForName === "" ? item.producedFor : item.producedForName}`}</span>
        <span className="text-dim">{dayWords(item.producedAt)}</span>
        <span className="text-[11.5px] text-dim">{STATE_WORDS[item.state] ?? item.state}</span>
        <span className="ml-auto flex flex-wrap gap-1">
          {item.downloadable ? (
            <Button variant="ghost" size="xs" onClick={() => onFetch(item)}>
              <Download aria-hidden />
              Download
            </Button>
          ) : null}
          {item.changeable && canSupersede && item.state === "current" ? (
            <Button variant="ghost" size="xs" onClick={() => onAsk({ kind: "supersede", item })}>
              Replace with a newer one
            </Button>
          ) : null}
          {item.changeable && item.state !== "archived" ? (
            <Button variant="ghost" size="xs" onClick={() => onAsk({ kind: "archive", item })}>
              Archive
            </Button>
          ) : null}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-dim">
        <span>{item.keptUntil === undefined ? item.keptBecause : `kept until ${dayWords(item.keptUntil)}, ${item.keptBecause}`}</span>
        <span>{sizeWords(item.bytesStored)}</span>
        {item.agentVersion === "" ? null : <span>{`version ${item.agentVersion}`}</span>}
      </div>
      {item.sources.length === 0 && item.knowledge.length === 0 ? null : (
        <div data-slot="artifact-provenance" className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
          <span className="text-dim">Built from</span>
          {item.sources.map((one) => (
            <Chip key={one} mono>
              {one}
            </Chip>
          ))}
          {item.knowledge.map((one) => (
            <Chip key={one.itemId}>{one.title}</Chip>
          ))}
        </div>
      )}
    </li>
  );
}

function saveFile(name: string, body: Blob): boolean {
  if (typeof URL.createObjectURL !== "function") {
    return false;
  }
  const address = URL.createObjectURL(body);
  const link = document.createElement("a");
  link.href = address;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(address);
  return true;
}

export function AgentArtifacts({ agentId }: { readonly agentId: string }) {
  const successorId = useId();
  const [filter, setFilter] = useState<ArtifactFilter>(NO_FILTER);
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentArtifactsApiPath(agentId, filter), version);
  const [asking, setAsking] = useState<Asking | null>(null);
  const [successor, setSuccessor] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  // The filter's choices outlive the request a filter makes, so the controls stay where they are
  // while the narrowed list is asked for. Each answer carries the people the reader sees whatever
  // the filter, so the latest answer's are the right ones.
  const [choices, setChoices] = useState<Choices | null>(null);
  const artifacts = answer.busy || answer.data === null ? null : readAgentArtifacts(answer.data);
  useEffect(() => {
    if (artifacts !== null && artifacts.unread === undefined) {
      setChoices((was) =>
        was !== null && was.kinds.join() === artifacts.kinds.join() && was.people.map((one) => one.principalId).join() === artifacts.people.map((one) => one.principalId).join()
          ? was
          : { kinds: artifacts.kinds, people: artifacts.people },
      );
    }
  }, [artifacts]);

  if (choices === null && answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (choices === null && (artifacts === null || artifacts.unread === undefined)) {
    return <LoadingState label={LOADING_ARTIFACTS} />;
  }
  const listed = artifacts?.artifacts ?? [];
  const candidates = (item: ArtifactItem) =>
    listed.filter((one) => one.artifactId !== item.artifactId && one.state === "current" && one.kind === item.kind);

  const fetchFile = async (item: ArtifactItem): Promise<void> => {
    const got = await requestFile(artifactFileApiPath(agentId, item.artifactId));
    if (!got.ok) {
      setSaid(got.failure.message);
      return;
    }
    setSaid(saveFile(fileName(item, got.type), got.body) ? null : CANNOT_SAVE_FILE);
  };

  const decide = async (one: Asking): Promise<void> => {
    setBusy(true);
    const result =
      one.kind === "archive"
        ? await request<unknown>(artifactArchiveApiPath(agentId, one.item.artifactId), { method: "POST" })
        : await request<unknown>(artifactSupersedeApiPath(agentId, one.item.artifactId), { method: "POST", body: { by: successor } });
    setBusy(false);
    setAsking(null);
    setSaid(result.ok ? null : result.failure.message);
    setVersion((count) => count + 1);
  };

  const filtered = filter !== NO_FILTER;
  const list =
    answer.failure !== null ? (
      <FailureState failure={answer.failure} />
    ) : artifacts === null ? (
      <LoadingState label={LOADING_ARTIFACTS} />
    ) : artifacts.unread !== undefined ? (
      <Note>{artifacts.unread}</Note>
    ) : listed.length === 0 ? (
      <Note>{filtered ? NOTHING_MATCHES : NOTHING_PRODUCED}</Note>
    ) : (
      <ul data-slot="artifact-list" className="m-0 flex list-none flex-col p-0">
        {listed.map((one) => (
          <ArtifactRow
            key={one.artifactId}
            item={one}
            onAsk={(next) => {
              setSuccessor(next.kind === "supersede" ? (candidates(next.item)[0]?.artifactId ?? "") : "");
              setAsking(next);
            }}
            onFetch={(item) => void fetchFile(item)}
            canSupersede={candidates(one).length > 0}
          />
        ))}
      </ul>
    );
  return (
    <div data-slot="agent-artifacts" className="flex min-w-0 flex-col gap-4">
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12.5px] text-crit">
          {said}
        </p>
      )}
      {artifacts === null ? null : <Figures artifacts={artifacts} />}
      <SectionCard title={ARTIFACTS_HEADING} lede="Documents, decks, reports, exports and images this agent made for people, newest first.">
        <div className="flex min-w-0 flex-col gap-3">
          {choices === null ? null : <Filters artifacts={choices} filter={filter} onFilter={setFilter} />}
          {list}
          {artifacts === null || artifacts.keptRule === "" ? null : <Note>{artifacts.keptRule}</Note>}
        </div>
      </SectionCard>
      <ConfirmDialog
        open={asking !== null}
        question={asking?.kind === "supersede" ? "Replace this with a newer version?" : "Archive this artifact?"}
        consequence={
          asking?.kind === "supersede"
            ? "It stays listed, marked as replaced by the one you choose, and nothing in it changes."
            : "It stays listed as archived and is no longer anybody's latest. Nothing is deleted."
        }
        details={
          asking?.kind === "supersede" ? (
            <div className="flex flex-col gap-1">
              <Label htmlFor={successorId}>The newer version</Label>
              <select id={successorId} className={CONTROL} value={successor} onChange={(event) => setSuccessor(event.target.value)}>
                {candidates(asking.item).map((one) => (
                  <option key={one.artifactId} value={one.artifactId}>
                    {`${KIND_WORDS[one.kind] ?? one.kind} for ${one.producedForName === "" ? one.producedFor : one.producedForName}, ${dayWords(one.producedAt)}`}
                  </option>
                ))}
              </select>
            </div>
          ) : undefined
        }
        confirmLabel={asking?.kind === "supersede" ? "Replace" : "Archive"}
        cancelLabel="Keep it"
        danger={asking?.kind === "archive"}
        busy={busy}
        onConfirm={() => {
          if (asking !== null && (asking.kind === "archive" || successor !== "")) {
            void decide(asking);
          }
        }}
        onCancel={() => setAsking(null)}
      />
    </div>
  );
}
