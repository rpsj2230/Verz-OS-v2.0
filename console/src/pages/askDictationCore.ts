/**
 * Dictation on Ask: the speech recognition the person's own browser carries, and nothing else
 * (M40.7.3).
 *
 * **There is no route, no vendor and no key behind this.** The owner decided (item 220 B) that a
 * person who would rather speak a question than type it is served by the recogniser built into
 * their browser. What is said goes to that browser and what comes back is text, which this module
 * hands to the question field. Nothing here calls `fetch`, opens a socket or names an address, so
 * there is nothing on our side to configure, secure, bill or break, and an install for a company
 * nobody here has met needs no setting for it. What the browser itself does with the sound is the
 * browser's business and is said so on the page (`AskDictation.tsx`).
 *
 * **Rejected: a speech-to-text tool in the registry with a record control that posts audio.** That
 * was the design this leaf was first written against. It needs a model or a vendor, a key held in
 * the vault, an upload route that must be rate limited and screened, and it sends a person's voice
 * to a server for a convenience a browser already provides.
 *
 * **The language is the browser's, never a constant here.** The console has no locale setting, so
 * the recogniser is asked for `navigator.language` and a hard-coded tag would be one company's
 * accent compiled into the product.
 *
 * **Only finished phrases are used, and they are appended to the question as it stands when they
 * arrive.** A recogniser that revises its guess (interim results) would rewrite a field the person
 * may be editing at the same moment, and replacing the field with the recogniser's view would
 * discard what they typed. So interim results are not asked for, and each finished phrase is added
 * after whatever is there: `appendSpoken`. The words are then ordinary typed text, editable.
 *
 * **Pure and injectable.** The recogniser is passed in as a constructor, so a test supplies a fake
 * and asserts both what is done with what it says and that nothing is sent anywhere.
 *
 * Task ids: M40.7.3
 */

/** One reading of what was said. */
export interface SpokenAlternative {
  readonly transcript: string;
}

/** One phrase as the recogniser reports it. Index zero is its best reading. */
export interface SpokenResult {
  readonly isFinal: boolean;
  readonly length: number;
  readonly [index: number]: SpokenAlternative | undefined;
}

export interface RecognitionEvent {
  readonly resultIndex: number;
  readonly results: {
    readonly length: number;
    readonly [index: number]: SpokenResult | undefined;
  };
}

export interface RecognitionErrorEvent {
  readonly error: string;
}

/** The part of the browser's recogniser this console uses. */
export interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export type RecognitionConstructor = new () => Recognition;

/** The names a browser exposes it under: the standard one and the long-standing prefixed one. */
const RECOGNITION_NAMES: readonly string[] = ["SpeechRecognition", "webkitSpeechRecognition"];

/**
 * The browser's recogniser, or null when it has none.
 *
 * Read off the scope it is given rather than off `window`, so a test hands in a plain object. The
 * cast is at the library boundary: the recogniser is not in the DOM typings this project compiles
 * against, and proving a structural match for a constructor the browser supplies buys nothing.
 */
export function findRecognition(scope: object): RecognitionConstructor | null {
  const held = scope as Record<string, unknown>;
  for (const name of RECOGNITION_NAMES) {
    const found = held[name];
    if (typeof found === "function") {
      return found as RecognitionConstructor;
    }
  }
  return null;
}

/** Why dictation could not go on, in the closed set the page has a sentence for. */
export type Problem = "denied" | "no-microphone" | "nothing-heard" | "language" | "failed";

/**
 * The problem a recogniser's error names, or null for one that is not a problem.
 *
 * `aborted` is what a recogniser reports when it is told to stop, which the person or the page
 * did on purpose. Every code not named here is a fault in the browser's own service and is
 * reported as one, rather than being guessed at.
 */
export function problemOf(code: string): Problem | null {
  switch (code) {
    case "aborted":
      return null;
    case "not-allowed":
    case "service-not-allowed":
      return "denied";
    case "audio-capture":
      return "no-microphone";
    case "no-speech":
      return "nothing-heard";
    case "language-not-supported":
      return "language";
    default:
      return "failed";
  }
}

export interface DictationHandlers {
  /** A finished phrase, trimmed and never empty. */
  readonly onSpoken: (words: string) => void;
  readonly onProblem: (problem: Problem) => void;
  /** Listening has stopped, for any reason. Called once. */
  readonly onEnd: () => void;
}

export interface Dictation {
  /** Stop listening and let what was already heard arrive. */
  stop(): void;
  /** Stop listening and drop anything not yet delivered. Nothing is called afterwards. */
  abort(): void;
}

/**
 * Start listening, in `language`, and report what is heard through `handlers`.
 *
 * A recogniser that refuses to start is a problem and an end, not an exception: the caller is a
 * button handler with nowhere to put one.
 */
export function startDictation(
  make: RecognitionConstructor,
  language: string,
  handlers: DictationHandlers,
): Dictation {
  const recognition = new make();
  let live = true;
  recognition.lang = language;
  recognition.continuous = true;
  recognition.interimResults = false;
  recognition.onresult = (event) => {
    if (!live) {
      return;
    }
    for (let at = event.resultIndex; at < event.results.length; at += 1) {
      const result = event.results[at];
      const words = result?.isFinal === true ? (result[0]?.transcript ?? "").trim() : "";
      if (words !== "") {
        handlers.onSpoken(words);
      }
    }
  };
  recognition.onerror = (event) => {
    const problem = live ? problemOf(event.error) : null;
    if (problem !== null) {
      handlers.onProblem(problem);
    }
  };
  recognition.onend = () => {
    if (live) {
      live = false;
      handlers.onEnd();
    }
  };
  try {
    recognition.start();
  } catch {
    live = false;
    handlers.onProblem("failed");
    handlers.onEnd();
  }
  return {
    stop() {
      try {
        recognition.stop();
      } catch {
        // Already stopped, which is what was asked for.
      }
    },
    abort() {
      live = false;
      try {
        recognition.abort();
      } catch {
        // Already stopped, which is what was asked for.
      }
    },
  };
}

/**
 * What was spoken, added after what was typed.
 *
 * One space between the two unless the typed text already ends in white space or is empty, and the
 * result is cut at `limit` when one is given, because the field's own limit is not applied to a
 * value set from code.
 */
export function appendSpoken(typed: string, spoken: string, limit?: number): string {
  const words = spoken.trim();
  if (words === "") {
    return typed;
  }
  const joined = typed === "" || /\s$/.test(typed) ? `${typed}${words}` : `${typed} ${words}`;
  return limit === undefined ? joined : joined.slice(0, limit);
}
