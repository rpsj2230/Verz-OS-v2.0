/**
 * A person's own conversations on Ask: the list, the search, one reopened, and the id a follow-up
 * continues by (M9.1.1, M9.1.2, M9.1.3).
 *
 * **Every address is the signed-in person's and none names anybody.** `brain.thread_routes` answers
 * for the caller alone, and a thread that is not theirs is the same 404 as one that does not exist,
 * drawn in the API's words.
 *
 * **The thread a question continues travels in the body, like the question.** The answer route
 * names the thread it kept an exchange in on the `x-thread-id` header; the page sends it back as
 * `thread` with the next question, and a new conversation is simply a question sent without one.
 *
 * **A reopened thread shows what the API sent and nothing about what it left out.** An answer given
 * under a grant since lost is absent from the messages, with no mark where it was: the person's
 * own questions always come back.
 *
 * **A wrong answer is marked with one of four kinds and no words.** The route keeps the kind and the
 * records the answer drew on as a note in the thread, which the learning signal counts; a sentence
 * saying what the right answer was would be a claim nobody checked, so the page offers no field for
 * one (`brain.chat.thread_store.A_CORRECTION_IS_A_SIGNAL_AND_NEVER_A_FACT`).
 *
 * Task ids: M9.1.1, M9.1.2, M9.1.3, M9.2.4
 */

import type { components } from "../api/schema";

/** Where the person's conversations are listed, searched and reopened, under the API base. */
export const THREADS_API_PATH = "/threads";
export const THREAD_SEARCH_API_PATH = "/threads/search";

/** The response header naming the thread an answer was kept in. */
export const THREAD_HEADER = "x-thread-id";

/** The longest search the route takes. */
export const MAX_SEARCH_CHARS = 200;

/** The address one thread is reopened at. The id is a UUID's text, and is encoded all the same. */
export function threadPath(threadId: string): string {
  return `${THREADS_API_PATH}/${encodeURIComponent(threadId)}`;
}

/** The address a search is asked at, or null for a search the route would refuse. */
export function threadSearchPath(words: string): string | null {
  const asked = words.trim();
  if (asked === "" || asked.length > MAX_SEARCH_CHARS) {
    return null;
  }
  return `${THREAD_SEARCH_API_PATH}?${new URLSearchParams({ q: asked }).toString()}`;
}

/** `brain.thread_routes.ThreadSummaryView`, as this console holds it. */
export interface ThreadSummary {
  readonly threadId: string;
  readonly title: string;
  readonly lastAt: string;
  readonly lastChannel: string;
}

/** `brain.thread_routes.ThreadMessageView`, as this console holds it. */
export interface ThreadMessage {
  readonly role: string;
  readonly at: string;
  readonly channel: string;
  readonly body: string;
}

/** `brain.thread_routes.ThreadView`, as this console holds it. */
export interface ThreadShown {
  readonly threadId: string;
  readonly title: string;
  readonly messages: readonly ThreadMessage[];
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** The list the API sent, or null when the body is not one. A row that is not a thread is left out. */
export function readThreads(payload: unknown): readonly ThreadSummary[] | null {
  const items = (payload as { items?: unknown } | null)?.items;
  if (!Array.isArray(items)) {
    return null;
  }
  return items.flatMap((one: unknown) => {
    const row = one as Record<string, unknown> | null;
    const threadId = text(row?.["thread_id"]);
    const lastAt = text(row?.["last_at"]);
    if (threadId === null || lastAt === null) {
      return [];
    }
    return [
      {
        threadId,
        title: text(row?.["title"]) ?? "",
        lastAt,
        lastChannel: text(row?.["last_channel"]) ?? "",
      },
    ];
  });
}

/** One reopened thread, or null when the body is not one. */
export function readThread(payload: unknown): ThreadShown | null {
  const body = payload as Record<string, unknown> | null;
  const threadId = text(body?.["thread_id"]);
  const messages = body?.["messages"];
  if (threadId === null || !Array.isArray(messages)) {
    return null;
  }
  return {
    threadId,
    title: text(body?.["title"]) ?? "",
    messages: messages.flatMap((one: unknown) => {
      const row = one as Record<string, unknown> | null;
      const role = text(row?.["role"]);
      const at = text(row?.["at"]);
      if (role === null || at === null) {
        return [];
      }
      return [{ role, at, channel: text(row?.["channel"]) ?? "", body: text(row?.["body"]) ?? "" }];
    }),
  };
}

/** The address the latest answer in one of the person's threads is marked wrong at. */
export function correctionPath(threadId: string): string {
  return `${threadPath(threadId)}/corrections`;
}

/** The address one of the person's threads is exported from as a file (M33.3.1.3). */
export function exportPath(threadId: string): string {
  return `${threadPath(threadId)}/export`;
}

/** `brain.thread_routes.ConversationTakenView`: the file once, its name, and what to say. */
export type ConversationTaken = components["schemas"]["ConversationTakenView"];

/**
 * The export just taken, or null when the body is not one. The document stays the string the API
 * sent, because its digest is what the export's record holds: parsed and written again, the saved
 * file would be one the record does not describe.
 */
export function readConversationTaken(payload: unknown): ConversationTaken | null {
  const body = payload as Record<string, unknown> | null;
  const filename = text(body?.["filename"]);
  const document = text(body?.["document"]);
  const told = text(body?.["told"]);
  if (filename === null || document === null || told === null) {
    return null;
  }
  return { filename, document, told };
}

/** `brain.chat.turns.CorrectionKind`, as the API's schema names it. */
export type CorrectionKind = components["schemas"]["CorrectionKind"];

/**
 * Every kind of wrong, in words, in the order the page offers them. Keyed by the schema's own
 * values, so a kind the product adds is a type error here until it has words.
 */
export const CORRECTION_WORDS: Readonly<Record<CorrectionKind, string>> = Object.freeze({
  wrong_fact: "It said something that is not true",
  missing: "It left out something that matters",
  misread_question: "It answered a different question",
  stale: "It was true once and is out of date",
});

/** `brain.chat.thread_store.CORRECTION_PREFIX`: how a marked answer is noted in the thread. */
export const CORRECTION_PREFIX = "correction:";

/** The body the correction route answers with, or null when it is not one. */
export function readCorrection(payload: unknown): CorrectionKind | null {
  const kind = text((payload as Record<string, unknown> | null)?.["kind"]);
  return kind !== null && kind in CORRECTION_WORDS ? (kind as CorrectionKind) : null;
}

/** A message's body in words: a correction note says which kind, anything else is as sent. */
export function messageWords(body: string): string {
  if (!body.startsWith(CORRECTION_PREFIX)) {
    return body;
  }
  const kind = body.slice(CORRECTION_PREFIX.length);
  const words = kind in CORRECTION_WORDS ? CORRECTION_WORDS[kind as CorrectionKind] : kind;
  return `You marked the answer wrong: ${words}.`;
}

/** Where a thread was last used, in words. The channel is the product's own closed list. */
export const CHANNEL_WORDS: Readonly<Record<string, string>> = Object.freeze({
  console: "on the web",
  lark: "in Lark",
  whatsapp: "in WhatsApp",
  email: "by email",
  telegram: "in Telegram",
  slack: "in Slack",
  teams: "in Teams",
});

/** A channel in words, or the stored word when this console has none for it. */
export function channelWords(channel: string): string {
  return CHANNEL_WORDS[channel] ?? channel;
}

/** Who said a message, in words. */
export function speaker(role: string): string {
  return role === "user" ? "You asked" : role === "assistant" ? "Answered" : "Noted";
}
