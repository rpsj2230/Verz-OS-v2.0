/**
 * The control on Ask that turns what a person says into the text of their question (M40.7.3).
 *
 * **It uses the speech recognition built into the person's browser and nothing of ours.** No
 * request is made by this control, so there is no route to refuse it and no key to set. The
 * decision and its reasons are in `askDictationCore.ts`.
 *
 * **A browser with no recogniser is told so in a sentence, not given a dead button.** Several
 * browsers have none, and a control that does nothing reads as a broken page. The sentence says
 * typing still works, which is true and is the reason nobody is blocked.
 *
 * **Every way it can fail has a sentence a person can act on.** A blocked microphone is the common
 * one, and the sentence says how to allow it, because "permission denied" tells nobody where the
 * setting is. Nothing here names a code the browser reported.
 *
 * **The button is a toggle, so its name does not change.** `aria-pressed` carries whether it is
 * listening, which a screen reader announces as pressed or not; a label that flipped between
 * Dictate and Stop would be read as a different control. What is happening is said in a status
 * region, which is on the page from the start because a live region added at the moment it speaks
 * is often not announced.
 *
 * **Listening stops when asking begins and when the page is left.** The question is sent as it
 * stands, so a phrase arriving after is words nobody will see; and a recogniser left running on a
 * page that has gone is a microphone left open. Anything not yet delivered is dropped.
 *
 * **It never takes focus and never sends.** The words arrive in the question field as ordinary
 * text, to be edited, and sending is the person's own press of Ask.
 *
 * Task ids: M40.7.3
 */

import { useEffect, useRef, useState } from "react";
import {
  findRecognition,
  startDictation,
  type Dictation,
  type Problem,
  type RecognitionConstructor,
} from "./askDictationCore";

export const DICTATE_LABEL = "Dictate your question";
export const DICTATION_LISTENING = "Listening. Speak your question, then press the button again to stop.";
export const DICTATION_FINISHED = "Dictation finished. Your words are in the question box, where you can change them.";
export const DICTATION_PRIVACY =
  "Dictation uses the speech recognition in your browser. Nothing you say is sent to this server.";
export const NO_DICTATION_HERE =
  "This browser cannot turn speech into text, so dictation is not available here. You can type your question instead.";

/** The sentence for each way listening can fail. */
export const DICTATION_PROBLEMS: Readonly<Record<Problem, string>> = Object.freeze({
  denied:
    "The microphone is blocked for this page. To allow it, open the site settings from the lock or settings icon beside the web address, set Microphone to Allow, then press the button again.",
  "no-microphone": "No microphone was found. Connect one, then press the button again.",
  "nothing-heard": "Nothing was heard. Press the button and speak again.",
  language: "This browser cannot recognise speech in your language. You can type your question instead.",
  failed: "Dictation stopped because the browser reported a fault. You can type your question instead.",
});

const NOTE_ID = "ask-dictation-note";

export function AskDictation({
  onSpoken,
  disabled,
}: {
  /** A finished phrase, to be appended to the question as it stands. */
  readonly onSpoken: (words: string) => void;
  /** True while a question is being answered, which stops listening. */
  readonly disabled: boolean;
}): React.JSX.Element {
  // Looked for once, at the first draw: a browser does not gain a recogniser while a page is open.
  const [recognition] = useState<RecognitionConstructor | null>(() => findRecognition(window));
  const [listening, setListening] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [heard, setHeard] = useState(false);
  const running = useRef<Dictation | null>(null);
  // The latest handler, so a phrase arriving after a re-draw is appended by the current one.
  const spoken = useRef(onSpoken);
  spoken.current = onSpoken;

  const abort = () => {
    running.current?.abort();
    running.current = null;
    setListening(false);
  };

  useEffect(() => {
    if (disabled) {
      running.current?.abort();
      running.current = null;
      setListening(false);
    }
  }, [disabled]);

  useEffect(
    () => () => {
      running.current?.abort();
      running.current = null;
    },
    [],
  );

  if (recognition === null) {
    return <p className="note">{NO_DICTATION_HERE}</p>;
  }

  const toggle = () => {
    if (listening) {
      running.current?.stop();
      return;
    }
    abort();
    setProblem(null);
    setHeard(false);
    setListening(true);
    const language = typeof navigator === "undefined" ? "" : navigator.language;
    // Only the current listening can call `onEnd`: an aborted one is silent by construction. It can
    // be called before `startDictation` returns, when the browser refuses to start.
    running.current = startDictation(recognition, language, {
      onSpoken(words) {
        setHeard(true);
        spoken.current(words);
      },
      onProblem(found) {
        setProblem(found);
      },
      onEnd() {
        running.current = null;
        setListening(false);
      },
    });
  };

  const status =
    problem !== null
      ? DICTATION_PROBLEMS[problem]
      : listening
        ? DICTATION_LISTENING
        : heard
          ? DICTATION_FINISHED
          : "";

  return (
    <div className="ask__dictation">
      <button
        type="button"
        className="button ask__dictate"
        aria-pressed={listening}
        aria-describedby={NOTE_ID}
        disabled={disabled}
        onClick={toggle}
      >
        {DICTATE_LABEL}
      </button>
      <p id={NOTE_ID} className="note">
        {DICTATION_PRIVACY}
      </p>
      <p className="note ask__dictation-status" role="status">
        {status}
      </p>
    </div>
  );
}
