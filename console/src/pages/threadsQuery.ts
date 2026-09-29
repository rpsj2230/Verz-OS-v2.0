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
 * Task ids: M9.1.1, M9.1.2, M9.1.3
 */

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
