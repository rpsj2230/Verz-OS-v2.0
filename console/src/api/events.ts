/**
 * How this console reads an event stream, and the four things it deliberately cannot do with
 * one.
 *
 * `POST /api/v1/answer` answers with `text/event-stream` rather than a document, so the one
 * route in this API that answers a question is also the one route whose body cannot be read
 * by `response.json()`. This module is the reading half, kept apart from `client.ts` for the
 * reason every split in this console is made: the fetch, the token and the failure shaping
 * live in one file, and what arrives over the wire is parsed by a pure function a test can
 * hand a string to.
 *
 * **The vocabulary is closed, and an event outside it reaches nothing.** `brain.gate.
 * streaming.Event` has five members and the module's whole argument is that a sixth, for a
 * model's intermediate reasoning, is what the type exists to refuse. A console that rendered
 * whatever name arrived would undo that from the other end: the day something upstream emits
 * a name nobody argued about, it would be on a screen. So `ANSWER_EVENTS` names the five and
 * `eventIn` returns null for anything else, which drops the frame rather than drawing it.
 *
 * **An id is read and discarded, because an id is a request to replay.** `encode` on the
 * Python side has no parameter for one, and the reason is `AN_EVENT_ID_IS_A_REQUEST_TO_REPLAY`:
 * a client that keeps a `Last-Event-ID` and reconnects with it has made knowing a string
 * sufficient to be served somebody else's answer. Nothing here keeps one, and there is no
 * reconnection in this console at all: a stream that ends has ended, and asking again is a
 * person pressing the button.
 *
 * **A data value's blank lines survive, because the sentence after one is load-bearing.**
 * The encoder writes one `data:` field per line precisely so that
 * `brain.gate.answer_cache.AGE_SEPARATOR`, which is two newlines, does not terminate the
 * event and take the sentence saying how old a cached answer is with it. A reader that
 * joined `data` fields with a space, or took only the first, would drop exactly that
 * sentence, which is the omission `AgeNotSurfacedError` exists to make impossible, arriving
 * through the client instead. They are joined with a single newline, which is what the format
 * says and what the encoder assumed.
 *
 * **Every line terminator is one break.** CRLF, CR and LF, longest first, for the reason the
 * encoder splits on all three: this repository writes CRLF by accident often enough to have a
 * note about it in `CLAUDE.md`, and a CR treated as an ordinary character puts a frame's
 * fields into one line.
 *
 * **A body that cannot be streamed is read whole, and that is said rather than hidden.** A
 * `Response` in a browser carries a `ReadableStream`; one built in a test environment, or by
 * a transport that buffered the whole response first, may not. The fallback reads the text
 * and parses the same frames through the same function, so the events are identical and only
 * their arrival is not. Nothing here invents a step, a delay or a progress bar for a stream it
 * did not watch arrive: see `A_STEP_NOT_SENT_IS_A_STEP_NOT_SHOWN`.
 */

/** Written down because a progress bar is the easiest thing in this console to fake. */
export const A_STEP_NOT_SENT_IS_A_STEP_NOT_SHOWN =
  "Every step on the answer screen is a frame the API sent, in the order it sent it. A " +
  "console that animated a plausible sequence while it waited would be describing work it " +
  "cannot see, and the labels it invented would be labels nobody held to the closed " +
  "vocabulary the API refuses to widen. When a body arrives in one piece the frames are " +
  "read in one piece, and the screen shows what was in it.";

/** The media type an event stream is served as. Held to `brain.api_routes.EVENT_STREAM`. */
export const EVENT_STREAM = "text/event-stream";

/** Every event name that may reach this console. `brain.gate.streaming.Event`'s five. */
export const ANSWER_EVENTS = ["step", "citation", "text", "done", "error"] as const;

export type AnswerEventName = (typeof ANSWER_EVENTS)[number];

/** One frame off the wire: a name from the closed vocabulary, and its data as it was sent. */
export interface AnswerEvent {
  readonly name: AnswerEventName;
  readonly data: string;
}

/** Every line terminator the format recognises, longest first so CRLF is one break. */
const TERMINATORS = ["\r\n", "\r", "\n"] as const;

function normalised(text: string): string {
  let out = text;
  for (const terminator of TERMINATORS.slice(0, -1)) {
    out = out.split(terminator).join("\n");
  }
  return out;
}

/**
 * The complete frames in a buffer, and whatever is left over.
 *
 * A trailing carriage return is held back rather than normalised, because it may be the first
 * half of a CRLF whose second half is in the next chunk; normalising it early would turn one
 * break into two and end a frame in the middle of its own data.
 */
export function framesIn(buffer: string): { frames: string[]; rest: string } {
  const held = buffer.endsWith("\r") ? buffer.slice(0, -1) : buffer;
  const trailing = buffer.endsWith("\r") ? "\r" : "";
  const parts = normalised(held).split("\n\n");
  const rest = parts.pop() ?? "";
  return { frames: parts.filter((frame) => frame !== ""), rest: rest + trailing };
}

/**
 * One frame as an event, or null for a frame this console has no name for.
 *
 * A comment frame, which the heartbeat is, has no `event` field and no data, so it parses to
 * nothing and is dropped here rather than being special-cased: a proxy counts it as traffic
 * and a reader has nothing to draw for it.
 */
export function eventIn(frame: string): AnswerEvent | null {
  let name = "";
  const data: string[] = [];
  for (const line of normalised(frame).split("\n")) {
    if (line.startsWith(":")) {
      continue;
    }
    const at = line.indexOf(":");
    const field = at === -1 ? line : line.slice(0, at);
    // One optional space after the colon belongs to the format rather than to the value.
    const value = at === -1 ? "" : line.slice(at + 1).replace(/^ /, "");
    if (field === "event") {
      name = value;
    } else if (field === "data") {
      data.push(value);
    }
    // `id` and `retry` are read as fields and kept nowhere. See the header: an id is a
    // resumption token, and this console never reconnects.
  }
  const known = (ANSWER_EVENTS as readonly string[]).includes(name);
  return known ? { name: name as AnswerEventName, data: data.join("\n") } : null;
}

/**
 * Every event in a response body, as they arrive.
 *
 * The reader path and the whole-body path produce the same events from the same parser, which
 * is what makes the second one honest rather than a second implementation. See the header.
 */
export async function* eventsOf(response: Response): AsyncGenerator<AnswerEvent> {
  const body = response.body;
  if (body === null) {
    for (const frame of framesIn(`${await response.text()}\n\n`).frames) {
      const event = eventIn(frame);
      if (event !== null) {
        yield event;
      }
    }
    return;
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (value !== undefined) {
        buffer += decoder.decode(value, { stream: true });
      }
      if (done) {
        // Whatever is left is a frame the server did not terminate. Ended here rather than
        // dropped, so the last chunk of an answer is not lost to a missing blank line.
        buffer += `${decoder.decode()}\n\n`;
      }
      const read = framesIn(buffer);
      buffer = read.rest;
      for (const frame of read.frames) {
        const event = eventIn(frame);
        if (event !== null) {
          yield event;
        }
      }
      if (done) {
        return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
