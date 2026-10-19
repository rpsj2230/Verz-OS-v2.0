/**
 * The questions a new person is offered before they have asked anything (M26.1.4).
 *
 * The route answers at most three, built from the caller's own department and kept only where they
 * hold what each needs, so nothing here decides what may be asked. A list that did not come back is
 * no list rather than an error: the question can still be typed. Choosing one puts it in the
 * field and sends nothing, so a person reads it before it is asked.
 */

import { useEffect, useState } from "react";
import { request } from "../api/client";

/** Where the questions are read from. */
export const WELCOME_API_PATH = "/welcome";

/** The line over them. */
export const TRY_ASKING = "You could start with one of these.";

/** The questions a body carries, or none when it is not the shape the route sends. */
export function readWelcome(payload: unknown): readonly string[] {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return [];
  }
  // A cast at the boundary, where proving a structural match buys nothing: every item is
  // checked to be a non-empty string below.
  const questions = (payload as Readonly<Record<string, unknown>>)["questions"];
  if (!Array.isArray(questions)) {
    return [];
  }
  return (questions as readonly unknown[]).filter(
    (one): one is string => typeof one === "string" && one.trim() !== "",
  );
}

export function AskWelcome({ onChoose }: { readonly onChoose: (question: string) => void }) {
  const [questions, setQuestions] = useState<readonly string[]>([]);
  useEffect(() => {
    let live = true;
    void (async () => {
      const told = await request<unknown>(WELCOME_API_PATH);
      if (live && told.ok) {
        setQuestions(readWelcome(told.data));
      }
    })();
    return () => {
      live = false;
    };
  }, []);
  if (questions.length === 0) {
    return null;
  }
  return (
    <div>
      <p className="note">{TRY_ASKING}</p>
      <ul>
        {questions.map((one) => (
          <li key={one}>
            <button type="button" className="button" onClick={() => onChoose(one)}>
              {one}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
