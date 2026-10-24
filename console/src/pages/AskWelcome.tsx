/**
 * The questions a new person is offered before they have asked anything (M26.1.4).
 *
 * The route answers at most three, built from the caller's own department and kept only where they
 * hold what each needs, so nothing here decides what may be asked. A list that did not come back is
 * no list rather than an error: the question can still be typed. Choosing one puts it in the
 * field and sends nothing, so a person reads it before it is asked.
 *
 * **A second list, from the person's own department's data, when the install has it on
 * (M34.1.1.2).** Each question names the system to check its answer in (M34.1.1.3). It is a second
 * read so the fixed questions are never waiting for it, and it is the same component, so there is
 * one welcome.
 */

import { useEffect, useState } from "react";
import { request } from "../api/client";
import { FROM_DATA_API_PATH, readFromData, type FromData } from "./adoptionCoverageQuery";
import { msg } from "../locale";

/** Where the questions are read from. */
export const WELCOME_API_PATH = "/welcome";

/** The line over them. */
export const TRY_ASKING = msg("console.ask.try_asking", "You could start with one of these.");

/** The line over the questions built from what your department has connected. */
export const FROM_YOUR_DATA = msg("console.ask.from_your_data", "Or ask about what is connected for your department.");

/** Beside a question built from data: where to open the same figure and compare. */
export const CHECK_IN = msg("console.ask.check_in", "Check the answer in");

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
  const [fromData, setFromData] = useState<readonly FromData[]>([]);
  useEffect(() => {
    let live = true;
    void (async () => {
      const told = await request<unknown>(WELCOME_API_PATH);
      if (live && told.ok) {
        setQuestions(readWelcome(told.data));
      }
    })();
    // The questions built from the department's own data are a second read, so the fixed ones are
    // never held up by it and a route that does not answer leaves them as they were.
    void (async () => {
      const told = await request<unknown>(FROM_DATA_API_PATH);
      if (live && told.ok) {
        setFromData(readFromData(told.data));
      }
    })();
    return () => {
      live = false;
    };
  }, []);
  if (questions.length === 0 && fromData.length === 0) {
    return null;
  }
  return (
    <div>
      {questions.length === 0 ? null : (
        <>
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
        </>
      )}
      {fromData.length === 0 ? null : (
        <>
          <p className="note">{FROM_YOUR_DATA}</p>
          <ul>
            {fromData.map((one) => (
              <li key={one.question}>
                <button type="button" className="button" onClick={() => onChoose(one.question)}>
                  {one.question}
                </button>{" "}
                <span className="note">
                  {CHECK_IN} {one.checkIn}.
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
