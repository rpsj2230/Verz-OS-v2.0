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
 * **The empty state says what the section is for.** An agent whose rule reaches nothing the reader
 * may open is shown the same words whether nothing exists or nothing is theirs, and the two ways to
 * add a document are offered only to a reader the API said may add one.
 *
 * Task ids: M39.9.1.1, M39.9.1.6
 */

import { FileText, Link2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import { useResource } from "../../api/useResource";
import { Chip, EmptyState, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { dayWords } from "../access/formParts";
import { documentAddress, verifiedWords } from "../knowledge/knowledgeDocuments";
import { KNOWLEDGE_PATH } from "../knowledgeQuery";
import { clauseWords } from "./agentCapabilitiesQuery";
import {
  agentKnowledgeApiPath,
  readAgentKnowledge,
  type AgentKnowledge as Knowledge,
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
export const NARROWS_NOTHING_OWN = "It narrows nothing of its own: it draws on whatever you may read.";

function ItemRow({ item }: { readonly item: KnowledgeItem }) {
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
        <span data-slot="knowledge-badge">{verifiedWords(item)}</span>
        {item.reviewBy === undefined ? null : <span>{`review by ${dayWords(item.reviewBy)}`}</span>}
      </div>
    </li>
  );
}

function Ways() {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button asChild variant="outline" size="sm" className="min-h-11 sm:min-h-8">
        <Link to={KNOWLEDGE_PATH}>
          <FileText aria-hidden />
          {ADD_A_FILE}
        </Link>
      </Button>
      <Button asChild variant="outline" size="sm" className="min-h-11 sm:min-h-8">
        <Link to={KNOWLEDGE_PATH}>
          <Link2 aria-hidden />
          {ADD_A_LINK}
        </Link>
      </Button>
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

export function AgentKnowledge({ agentId }: { readonly agentId: string }) {
  const first = useResource<unknown>(agentKnowledgeApiPath(agentId, 0), 0);
  const [later, setLater] = useState<readonly KnowledgeItem[]>([]);
  const [more, setMore] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const knowledge = first.busy || first.data === null ? null : readAgentKnowledge(first.data);

  if (first.failure !== null) {
    return <FailureState failure={first.failure} />;
  }
  if (knowledge === null) {
    return <LoadingState label={LOADING_KNOWLEDGE} />;
  }

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
          <EmptyState title={EMPTY_TITLE} description={EMPTY_BODY} action={<Ways />} />
        </div>
      ) : (
        <Note>{NOTHING_YOURS_TO_SEE}</Note>
      )
    ) : (
      <>
        <ul data-slot="knowledge-list" className="m-0 flex list-none flex-col p-0">
          {items.map((one) => (
            <ItemRow key={one.itemId} item={one} />
          ))}
        </ul>
        {hasMore ? (
          <div>
            <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" disabled={busy} onClick={() => void showMore()}>
              {SHOW_MORE}
            </Button>
          </div>
        ) : null}
        {knowledge.canAdd ? <Ways /> : null}
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
          {body}
          {knowledge.keptRule === "" ? null : <Note>{knowledge.keptRule}</Note>}
        </div>
      </SectionCard>
    </div>
  );
}
