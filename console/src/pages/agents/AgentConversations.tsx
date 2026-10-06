/**
 * An agent's Conversations section: the reader's own threads it answered in, each with who took
 * part, when it was last used, its first question and how the agent's latest run there ended.
 *
 * **Everything drawn is the route's answer.** `brain.agent_conversation_routes` lists the reader's
 * own threads and nobody else's, because a thread has one human and a reader sees only their own
 * (`brain.console.agent_conversations`). So there is no "related to me" filter: every row already
 * is, and a filter that can never change the list is not drawn.
 *
 * **A failed run says failed and shows nothing else.** The row carries the run state the thread
 * recorded, and a failed run's turn holds no words, so the section never has model output to show
 * for it. A run recorded before states were kept says so rather than guessing.
 *
 * Task ids: M39.8.9
 */

import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { FailureState, LoadingState, Note } from "../../components/kit";
import { ASK_ADDRESS } from "../Ask";
import { channelWords } from "../threadsQuery";

export const LOADING_CONVERSATIONS = "Reading your conversations with this agent.";
export const NO_CONVERSATIONS = "You have not asked this agent anything yet.";
export const OPEN_ASK = "Ask this agent a question";
export const YOU = "You";

export function agentConversationsApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/conversations`;
}

/** How a run ended, as a person reads it. */
export const STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  answered: "Answered",
  abstained: "Declined",
  degraded: "Partly answered",
  failed: "Failed",
});

/** What a row says when its run state was not recorded. */
export const STATE_NOT_RECORDED = "Not recorded";

interface Participant {
  readonly agentId: string;
  readonly displayName: string;
}

export interface Conversation {
  readonly threadId: string;
  readonly title: string;
  readonly lastAt: string;
  readonly lastChannel: string;
  readonly agents: readonly Participant[];
  readonly state: string | null;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through a type test below.
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

function participants(value: unknown): Participant[] {
  return (Array.isArray(value) ? (value as readonly unknown[]) : [])
    .map(fieldsOf)
    .filter((one): one is Fields => one !== null && typeof one["agent_id"] === "string" && typeof one["display_name"] === "string")
    .map((one) => ({ agentId: String(one["agent_id"]), displayName: String(one["display_name"]) }));
}

/** The conversations read out of a body, or null when the body is not an object at all. */
export function readConversations(payload: unknown): readonly Conversation[] | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  return (Array.isArray(fields["items"]) ? (fields["items"] as readonly unknown[]) : [])
    .map(fieldsOf)
    .filter((one): one is Fields => one !== null && typeof one["thread_id"] === "string" && typeof one["last_at"] === "string")
    .map((one) => ({
      threadId: String(one["thread_id"]),
      title: typeof one["title"] === "string" ? one["title"] : "",
      lastAt: String(one["last_at"]),
      lastChannel: typeof one["last_channel"] === "string" ? one["last_channel"] : "",
      agents: participants(one["agents"]),
      state: typeof one["state"] === "string" ? one["state"] : null,
    }));
}

const RELATIVE = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });

/** How long ago an instant was, in words, from `now`. An instant that does not parse is itself. */
export function relativeWhen(stamp: string, now: Date): string {
  const at = new Date(stamp);
  if (Number.isNaN(at.getTime())) {
    return stamp;
  }
  const seconds = Math.round((at.getTime() - now.getTime()) / 1000);
  const steps: readonly [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 365 * 24 * 3600],
    ["month", 30 * 24 * 3600],
    ["week", 7 * 24 * 3600],
    ["day", 24 * 3600],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) {
      return RELATIVE.format(Math.round(seconds / size), unit);
    }
  }
  return RELATIVE.format(0, "minute");
}

/** Who took part, in words: the reader, then each agent that answered. */
export function participantWords(agents: readonly Participant[]): string {
  return [YOU, ...agents.map((one) => one.displayName)].join(", ");
}

export function stateWords(state: string | null): string {
  return state === null ? STATE_NOT_RECORDED : (STATE_WORDS[state] ?? state);
}

export function AgentConversations({ agentId, now = new Date() }: { readonly agentId: string; readonly now?: Date }) {
  const answer = useResource<unknown>(agentConversationsApiPath(agentId));
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  const conversations = answer.data === null ? null : readConversations(answer.data);
  if (answer.busy || conversations === null) {
    return <LoadingState label={LOADING_CONVERSATIONS} />;
  }
  return (
    <div data-slot="agent-conversations" className="flex min-w-0 flex-col gap-2 text-[12.5px]">
      {conversations.length === 0 ? (
        <Note>{NO_CONVERSATIONS}</Note>
      ) : (
        <ul data-slot="conversations-listed" className="m-0 flex list-none flex-col p-0">
          {conversations.map((one) => (
            <li key={one.threadId} data-state={one.state ?? "unrecorded"} className="flex min-w-0 flex-col gap-0.5 border-b border-line py-2 last:border-b-0">
              <span className="min-w-0 text-ink [overflow-wrap:anywhere]">{one.title}</span>
              <span className="text-dim">
                {participantWords(one.agents)} · {relativeWhen(one.lastAt, now)}
                {one.lastChannel === "" ? "" : `, ${channelWords(one.lastChannel)}`}
              </span>
              <span className={one.state === "failed" ? "font-medium text-crit" : "text-dim"}>{stateWords(one.state)}</span>
            </li>
          ))}
        </ul>
      )}
      <Link to={ASK_ADDRESS} className="w-fit text-acc-text underline-offset-4 hover:underline">
        {OPEN_ASK}
      </Link>
    </div>
  );
}
