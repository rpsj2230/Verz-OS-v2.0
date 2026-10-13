/**
 * An agent's Knowledge section: the documents it draws on, each with its kind, where it sits, who
 * added it and when, whether it is verified or due for review, and a way in for what is missing.
 *
 * **Every row is the route's, drawn as sent.** The list is the company's documents the reader may
 * open that the agent's rule reaches, newest first. It keeps no store of the agent's own, and says
 * so beside the list, because nobody reads through an agent a document they could not open
 * anywhere else. A longer list is a second request for the next page, never a pass over what the
 * browser holds, and nothing on the page counts anything the reader may not see: "show more"
 * appears when the API said a page was full and says no more than that.
 *
 * **Adding is the Knowledge page's own form, pointed at this agent's address.** `AddFileForm` and
 * `AddLinkForm` are drawn here with the options the API offers this person and the department the
 * rule already draws on as the default; what they send reaches the same door. The answer says in one
 * sentence whether this agent draws on what was added. When it does not, it names the clause of the
 * rule that excludes it and offers the one next step, the draft that widens the rule, and nothing is
 * changed for any agent by having added it.
 *
 * **The empty state says what the section is for.** An agent whose rule reaches nothing the reader
 * may open is shown the same words whether nothing exists or nothing is theirs, and the two ways to
 * add a document are offered only to a reader the API said may add one.
 *
 * **Other sources are listed from the workspace the page already read** (`OtherSources`): each
 * connected source and each pinned skill, named by kind and linking to the page that owns it, so one
 * place shows the agent's whole context and nothing is copied or asked for twice.
 *
 * **Retiring a document and fetching a link again are offered under a row** (`ItemActs`), only where
 * the API said this reader may act on it, and both are the Knowledge page's own acts: a document is
 * the company's, so retiring one withdraws it for every agent. **How it arrived is said as recorded**:
 * a file, a link, or "not recorded" for a document added before it was kept, never read off its text.
 *
 * Task ids: M39.9.1.5, M39.9.1.7, M39.2.3.2, M39.9.1.1, M39.9.1.2, M39.9.1.3, M39.9.1.4, M39.9.1.6
 */

import { FileText, Link2, Plug, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import { useResource } from "../../api/useResource";
import { Chip, EmptyState, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { dayWords } from "../access/formParts";
import { documentAddress, verifiedWords } from "../knowledge/knowledgeDocuments";
import type { ConnectorStrip, SkillPin } from "../agentQuery";
import { connectorAddress } from "../connectors/connectorSources";
import { AddFileForm, AddLinkForm, type Door } from "../knowledge/addForms";
import { readUploadOptions, UPLOAD_OPTIONS_API_PATH } from "../knowledgeQuery";
import { skillAddress } from "../skillsQuery";
import { clauseWords } from "./agentCapabilitiesQuery";
import { ItemActs } from "./AgentKnowledgeActs";
import {
  agentKnowledgeApiPath,
  agentKnowledgeLinkApiPath,
  agentKnowledgeUploadApiPath,
  readAgentKnowledge,
  readKnowledgeAdded,
  type KnowledgeAdded,
  type AgentKnowledge as Knowledge,
  type UseFigures,
  type Arrival,
  type KnowledgeItem,
} from "./agentKnowledgeQuery";

export const KNOWLEDGE_HEADING = "What it draws on";
export const KNOWLEDGE_LEDE = "The company's documents this agent answers from, that you may open, newest first.";
export const LOADING_KNOWLEDGE = "Loading what this agent draws on.";
export const EMPTY_TITLE = "Add some context for this agent";
export const EMPTY_BODY =
  "Add a file or a web page and this agent can answer from it once its rule reaches it. What you add is the company's own document, with the access you choose, and nobody reads through the agent anything they could not open anyway.";
export const NOTHING_YOURS_TO_SEE = "Nothing this agent draws on is yours to see yet.";
export const ADD_A_FILE = "Add a file";
export const ADD_A_LINK = "Add a web page by its link";
export const SHOW_MORE = "Show more";
export const OTHER_SOURCES_HEADING = "Other sources it draws on";
export const OTHER_SOURCES_LEDE =
  "Connected sources and the skills it carries, listed by kind. Each is managed on its own page and none is copied here.";
export const WIDEN_THROUGH_A_DRAFT = "Widen what it draws on, through a draft";
export const DOES_NOT_MATCH = "It does not match";
export const NARROWS_NOTHING_OWN = "It narrows nothing of its own: it draws on whatever you may read.";

/** What the figure beside an item says. Absent while nothing is counted, and never drawn as nought. */
export function usesWords(uses: number, figures: UseFigures): string {
  if (uses === 0) {
    return `Not cited in the last ${String(figures.windowDays)} days`;
  }
  return `Cited in ${uses === 1 ? "1 answer" : `${String(uses)} answers`} in the last ${String(figures.windowDays)} days`;
}

export const ARRIVED_AS_A_FILE = "added as a file";
export const ARRIVED_AS_A_LINK = "added from a link";
export const ARRIVAL_NOT_RECORDED = "how it was added is not recorded";

export function arrivalWords(arrival: Arrival): string {
  return arrival === "file" ? ARRIVED_AS_A_FILE : arrival === "link" ? ARRIVED_AS_A_LINK : ARRIVAL_NOT_RECORDED;
}

function ItemRow({
  agentId,
  item,
  figures,
  onChanged,
}: {
  readonly agentId: string;
  readonly item: KnowledgeItem;
  readonly figures?: UseFigures | undefined;
  readonly onChanged: () => void;
}) {
  const addedBy = item.addedByName === "" ? undefined : item.addedByName;
  const day = dayWords(item.addedAt);
  const added = [addedBy === undefined ? null : `added by ${addedBy}`, day === "" ? null : day].filter((one): one is string => one !== null);
  return (
    <li data-slot="knowledge-item" className="flex flex-col gap-1.5 border-b border-line py-2.5 text-[13px] last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        <FileText aria-hidden className="size-4 text-dim" />
        <Link to={documentAddress(item.itemId)} className="font-medium text-ink underline-offset-4 hover:underline">
          {item.title}
        </Link>
        <Chip>{item.kindLabel}</Chip>
        {item.due ? <Chip tone="requested">Due for review</Chip> : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-dim">
        {item.place === "" ? null : <span>{`in ${item.place}`}</span>}
        {added.length === 0 ? null : <span>{added.join(", ")}</span>}
        <span data-slot="knowledge-arrival">{arrivalWords(item.arrivedAs)}</span>
        <span data-slot="knowledge-badge">{verifiedWords(item)}</span>
        {item.reviewBy === undefined ? null : <span>{`review by ${dayWords(item.reviewBy)}`}</span>}
        {item.uses === undefined || figures === undefined ? null : <span data-slot="knowledge-uses">{usesWords(item.uses, figures)}</span>}
      </div>
      <ItemActs agentId={agentId} item={item} onChanged={onChanged} />
    </li>
  );
}

type Way = "file" | "link";

function Ways({ shown, onShow }: { readonly shown: Way | null; readonly onShow: (way: Way | null) => void }) {
  return (
    <div data-slot="knowledge-ways" className="flex flex-wrap items-center gap-3">
      <Button variant={shown === "file" ? "secondary" : "outline"} size="sm" className="min-h-11 sm:min-h-8" aria-pressed={shown === "file"} onClick={() => onShow(shown === "file" ? null : "file")}>
        <FileText aria-hidden />
        {ADD_A_FILE}
      </Button>
      <Button variant={shown === "link" ? "secondary" : "outline"} size="sm" className="min-h-11 sm:min-h-8" aria-pressed={shown === "link"} onClick={() => onShow(shown === "link" ? null : "link")}>
        <Link2 aria-hidden />
        {ADD_A_LINK}
      </Button>
    </div>
  );
}

function Answer({ added, onWiden, onClose }: { readonly added: KnowledgeAdded; readonly onWiden?: (() => void) | undefined; readonly onClose: () => void }) {
  return (
    <div data-slot="knowledge-added" role="status" className="flex flex-col gap-2 rounded-md border border-line p-3 text-[13px]">
      <div className="flex items-start gap-2">
        <p className="m-0 flex-1 text-ink">
          <span className="font-medium">{added.title}</span>
          {`. ${added.said}`}
        </p>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label="Dismiss" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </div>
      {added.reached || added.blocking.length === 0 ? null : (
        <p data-slot="knowledge-blocking" className="m-0 text-[12px] text-dim">
          {`${DOES_NOT_MATCH}: ${added.blocking.map(clauseWords).join(", and ")}.`}
        </p>
      )}
      {added.reached || !added.canWiden || onWiden === undefined ? null : (
        <div>
          <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" onClick={onWiden}>
            {WIDEN_THROUGH_A_DRAFT}
          </Button>
        </div>
      )}
    </div>
  );
}

function Rule({ knowledge }: { readonly knowledge: Knowledge }) {
  const described = knowledge.rule.length === 0 ? NARROWS_NOTHING_OWN : `It draws on ${knowledge.rule.map(clauseWords).join(", and ")}.`;
  return (
    <p data-slot="knowledge-rule" className="m-0 text-[12.5px] text-body">
      {described}
    </p>
  );
}

/**
 * The agent's other sources, from the workspace the page already read: each connected source and
 * each skill it is pinned to, named by kind and linking to the page that owns it. No second copy of
 * their data is kept and nothing is asked for, so this can only say what the Profile already says.
 */
export function OtherSources({ connectors, skills }: { readonly connectors: ConnectorStrip; readonly skills: readonly SkillPin[] }) {
  if (connectors.shown.length === 0 && skills.length === 0) {
    return null;
  }
  return (
    <SectionCard title={OTHER_SOURCES_HEADING} lede={OTHER_SOURCES_LEDE}>
      <ul data-slot="knowledge-other-sources" className="m-0 flex list-none flex-col gap-2 p-0 text-[13px]">
        {connectors.shown.map((one) => (
          <li key={`connector-${one.source}`} className="flex flex-wrap items-center gap-2">
            <Plug aria-hidden className="size-4 text-dim" />
            <Chip>Connected source</Chip>
            <Link to={connectorAddress(one.source)} className="font-medium text-ink underline-offset-4 hover:underline">
              {one.source}
            </Link>
            {one.presence === "attached" ? null : <span className="text-[11.5px] text-dim">{one.presence}</span>}
          </li>
        ))}
        {connectors.overflow > 0 ? (
          <li key="connectors-more">
            <Chip tone="requested">{`${String(connectors.overflow)} more connected sources on this agent`}</Chip>
          </li>
        ) : null}
        {skills.map((one) => (
          <li key={`skill-${one.digest}`} className="flex flex-wrap items-center gap-2">
            <Sparkles aria-hidden className="size-4 text-dim" />
            <Chip>Skill</Chip>
            <Link to={skillAddress(one.name)} className="font-medium text-ink underline-offset-4 hover:underline">
              {one.name}
            </Link>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

export function AgentKnowledge({
  agentId,
  onWiden,
  connectors,
  skills,
}: {
  readonly agentId: string;
  readonly onWiden?: (() => void) | undefined;
  readonly connectors?: ConnectorStrip | undefined;
  readonly skills?: readonly SkillPin[] | undefined;
}) {
  const [version, setVersion] = useState(0);
  const first = useResource<unknown>(agentKnowledgeApiPath(agentId, 0), version);
  const [later, setLater] = useState<readonly KnowledgeItem[]>([]);
  const [more, setMore] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [way, setWay] = useState<Way | null>(null);
  const [added, setAdded] = useState<KnowledgeAdded | null>(null);
  const knowledge = first.busy || first.data === null ? null : readAgentKnowledge(first.data);
  // What this person may add and where is the Knowledge page's own question, asked once and only
  // of a reader the section says may add.
  const offered = useResource<unknown>(knowledge?.canAdd === true ? UPLOAD_OPTIONS_API_PATH : null);
  const options = offered.failure === null && offered.data !== null ? readUploadOptions(offered.data) : null;

  if (first.failure !== null) {
    return <FailureState failure={first.failure} />;
  }
  if (knowledge === null) {
    return <LoadingState label={LOADING_KNOWLEDGE} />;
  }

  const door: Door = {
    upload: (kind, level, department) => agentKnowledgeUploadApiPath(agentId, kind, level, department),
    link: agentKnowledgeLinkApiPath(agentId),
    ...(knowledge.addInto === undefined ? {} : { department: knowledge.addInto }),
  };
  const onAdded = (answer: unknown): void => {
    setAdded(readKnowledgeAdded(answer));
    setWay(null);
    setLater([]);
    setMore(null);
    setVersion((count) => count + 1);
  };
  // A retired or replaced document changes the list, so the first page is asked for again.
  const onChanged = (): void => {
    setLater([]);
    setMore(null);
    setVersion((count) => count + 1);
  };
  const ways = knowledge.canAdd && options !== null ? <Ways shown={way} onShow={setWay} /> : null;
  const form =
    options === null || way === null ? null : (
      <div data-slot="knowledge-form" className="max-w-xl">
        {way === "file" ? <AddFileForm options={options} onAdded={onAdded} door={door} /> : <AddLinkForm options={options} onAdded={onAdded} door={door} />}
      </div>
    );

  const items = [...knowledge.items, ...later];
  const hasMore = more ?? knowledge.more;
  const showMore = async (): Promise<void> => {
    setBusy(true);
    const result = await request<unknown>(agentKnowledgeApiPath(agentId, items.length));
    setBusy(false);
    if (!result.ok) {
      setSaid(result.failure.message);
      return;
    }
    const next = readAgentKnowledge(result.data);
    setSaid(null);
    if (next !== null) {
      setLater((were) => [...were, ...next.items.filter((one) => ![...knowledge.items, ...were].some((had) => had.itemId === one.itemId))]);
      setMore(next.more);
    }
  };

  const body =
    knowledge.unread !== undefined ? (
      <Note>{knowledge.unread}</Note>
    ) : items.length === 0 ? (
      knowledge.canAdd ? (
        <div data-slot="knowledge-empty">
          <EmptyState title={EMPTY_TITLE} description={EMPTY_BODY} action={ways} />
        </div>
      ) : (
        <Note>{NOTHING_YOURS_TO_SEE}</Note>
      )
    ) : (
      <>
        <ul data-slot="knowledge-list" className="m-0 flex list-none flex-col p-0">
          {items.map((one) => (
            <ItemRow key={one.itemId} agentId={agentId} item={one} figures={knowledge.useFigures} onChanged={onChanged} />
          ))}
        </ul>
        {hasMore ? (
          <div>
            <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" disabled={busy} onClick={() => void showMore()}>
              {SHOW_MORE}
            </Button>
          </div>
        ) : null}
        {ways}
      </>
    );

  return (
    <div data-slot="agent-knowledge" className="flex min-w-0 flex-col gap-4">
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12.5px] text-crit">
          {said}
        </p>
      )}
      <SectionCard title={KNOWLEDGE_HEADING} lede={KNOWLEDGE_LEDE}>
        <div className="flex min-w-0 flex-col gap-3">
          {knowledge.unread === undefined ? <Rule knowledge={knowledge} /> : null}
          {added === null ? null : <Answer added={added} onWiden={onWiden} onClose={() => setAdded(null)} />}
          {body}
          {form}
          {knowledge.useFigures === undefined ? null : <Note>{`Figures beside each document count ${knowledge.useFigures.basis}.`}</Note>}
          {knowledge.keptRule === "" ? null : <Note>{knowledge.keptRule}</Note>}
        </div>
      </SectionCard>
      <OtherSources connectors={connectors ?? { shown: [], overflow: 0 }} skills={skills ?? []} />
    </div>
  );
}
