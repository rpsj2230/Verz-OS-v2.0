/**
 * Asking past a window, on the Ask screen: the person is told when they may ask again.
 *
 * The API answers a question asked past a window with a 429 whose message says, in words, how
 * long to wait, and whose `Retry-After` says the same in seconds (`brain.ops.limits.
 * refusal_sentence`, `retry_after_header`). This screen shows the message the API sent and adds
 * no interpretation, which is `api/errors.A_404_IS_NOT_AN_EXPLANATION`'s rule for every failure,
 * so what is held here is that the sentence reaches the person whole, with its reference, and
 * that no answer is drawn beside it.
 *
 * A file of its own rather than a case in `tests/ask-page.test.tsx`, because the Ask screen
 * belongs to another package in this wave and a shared test file is a merge nobody planned.
 *
 * Task ids: M23.1.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { ASK_ADDRESS, ASK_LABEL } from "../src/pages/Ask";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const CONSOLE_ORIGIN = "https://console.test";
const ANSWER_API = "/api/v1/answer";

/** What `brain.ops.limits.refusal_sentence` says for a person's own window, forty seconds out. */
const SAID =
  "You have asked more often in the last minute than this install allows. " +
  "You can ask again in 40 seconds.";

describe("a question asked past the window", () => {
  test("says in the API's words when the person may ask again, with its reference", async () => {
    // What breaks if this is deleted: the screen can replace the API's sentence with a fallback
    // for its status, which says a request was not accepted and not when to come back, and the
    // person presses the button again at once and is refused again.
    const idp = fakeIdentityProvider({
      api(url) {
        if (new URL(url, CONSOLE_ORIGIN).pathname !== ANSWER_API) {
          return null;
        }
        return new Response(JSON.stringify({ message: SAID, trace_id: "trace-limited" }), {
          status: 429,
          headers: { "content-type": "application/json", "retry-after": "40" },
        });
      },
    });
    const loaded = await loadConsole({ idp, path: ASK_ADDRESS });
    await signIn(loaded);
    const { routes } = await import("../src/App");
    const router = createMemoryRouter(routes, { initialEntries: [ASK_ADDRESS] });
    const { container } = render(<RouterProvider router={router} />);
    await waitFor(() => {
      if (!container.querySelector("textarea")) {
        throw new Error("the page has not arrived");
      }
    });

    fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, {
      target: { value: "what is the price of WEB-1001" },
    });
    const button = [...container.querySelectorAll("button")].find((one) => one.textContent === ASK_LABEL);
    fireEvent.click(button as HTMLButtonElement);

    await waitFor(() => {
      expect(container.querySelector(".notice__body > p")?.textContent).toBe(SAID);
    });
    expect(container.querySelector(".notice__trace code")?.textContent).toBe("trace-limited");
    expect(container.querySelector(".ask__answer")).toBeNull();
  });
});
