/**
 * A refused write draws each of the API's problems beside the input it names, and lists the rest
 * under the failure notice.
 *
 * On 2026-09-17 the API began listing problems on every validation refusal it writes, by the place
 * in the request each one names. Four forms in this console drew such a list and forty did not, so a
 * refusal about one box reached a person as a sentence under a heading with the box unnamed. The
 * matching is `api/problems.ts`, the drawing is `ui/FieldProblems.tsx` and `ui/FailureNotice.tsx`,
 * and the generated forms map the same problems onto the library's own error slots in
 * `components/formSchema.ts`. This file holds one hand-built form and one generated form to it,
 * because those are the two ways a form is written here, and each refusal test has a sibling where
 * the write succeeds and nothing is drawn.
 *
 * Task ids: M27.8.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { RJSFSchema } from "@rjsf/utils";
import { beforeAll, describe, expect, test } from "vitest";
import type { ApiFailure, FieldProblem } from "../src/api/errors";
import { problemsFor, unmatchedProblems } from "../src/api/problems";
import { SchemaForm } from "../src/components/SchemaForm";
import { ACCOUNT_LABEL, LINK_A_SIGN_IN, LINK_BUTTON, LOADING_LINKS, PERSON_LABEL } from "../src/pages/sessions/SignInLinksPage";
import { WHAT_WAS_NOT_ACCEPTED } from "../src/ui/FailureNotice";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const LINKS_OPERATION = "/api/v1/govern/sign-ins";
const LINK_OPERATION = "/api/v1/sign-ins";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/SignInLinks");
}, 60_000);

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("which problem belongs to which input", () => {
  test("a problem is matched by the exact name of an input and by nothing looser", () => {
    // What breaks if this is deleted: `rungs.0.attempts` drawn beside any input called `attempts`,
    // which on a form with two of them is the wrong box, or a problem with the request as a whole
    // drawn beside the first input whose name happens to be empty.
    const problems: FieldProblem[] = [
      { field: "rungs.0.attempts", code: "too_big", message: "NESTED" },
      { field: "attempts", code: "too_big", message: "FLAT" },
      { field: "", code: "json_invalid", message: "WHOLE" },
    ];
    expect(problemsFor(problems, "attempts")).toEqual(["FLAT"]);
    expect(problemsFor(problems, ["rungs.0.attempts"])).toEqual(["NESTED"]);
    expect(problemsFor(problems, "")).toEqual([]);
    expect(unmatchedProblems(problems, ["attempts", ""]).map((one) => one.message)).toEqual(["NESTED", "WHOLE"]);
    expect(unmatchedProblems(problems, ["attempts", "rungs.0.attempts"]).map((one) => one.message)).toEqual([
      "WHOLE",
    ]);
  });
});

/** The Sign-in links page with its link drawer open. The drawer is a dialog outside the page. */
async function linksScreen(answerTheLink: () => Response): Promise<{ container: HTMLElement; drawer: HTMLElement }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      if (path === LINK_OPERATION && init?.method === "POST") {
        return answerTheLink();
      }
      if (path === LINKS_OPERATION) {
        return json({ items: [], truncated: false, account: "ACCOUNT", unlinking: "UNLINKING", last_administrator: "LAST" });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { SignInLinks } = await import("../src/pages/SignInLinks");
  const router = createMemoryRouter([{ path: "/sign-in-links", element: <SignInLinks /> }], {
    initialEntries: ["/sign-in-links"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.textContent?.includes(LOADING_LINKS)) {
      throw new Error("still loading");
    }
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: LINK_A_SIGN_IN }));
  });
  return { container, drawer: await screen.findByRole("dialog") };
}

function input(drawer: HTMLElement, label: string): HTMLInputElement {
  return within(drawer).getByLabelText(label) as HTMLInputElement;
}

async function link(drawer: HTMLElement): Promise<void> {
  fireEvent.change(input(drawer, ACCOUNT_LABEL), { target: { value: "9a8b7c6d-0000-4000-8000-0000000000aa" } });
  fireEvent.change(input(drawer, PERSON_LABEL), { target: { value: "u_one" } });
  await act(async () => {
    fireEvent.click(within(drawer).getByRole("button", { name: LINK_BUTTON }));
  });
}

describe("a hand-built form", () => {
  test("a validation refusal draws each problem beside its own input and lists the rest under the notice", async () => {
    // What breaks if this is deleted: the refusal the staging install drew as one sentence, with the
    // box it was about unnamed; a problem with no input dropped rather than said; or an input the
    // API never named marked invalid beside one it did.
    const { drawer } = await linksScreen(() =>
      json(
        {
          message: "Some of what was sent was not accepted.",
          trace_id: "trace-422",
          problems: [
            { field: "principal_id", code: "string_too_long", message: "PERSON-PROBLEM-SENTINEL" },
            { field: "", code: "json_invalid", message: "WHOLE-BODY-SENTINEL" },
            { field: "expected_hash", code: "missing", message: "NO-INPUT-SENTINEL" },
          ],
          second_factor_needed: false,
        },
        422,
        { "x-trace-id": "trace-422" },
      ),
    );

    await link(drawer);

    await waitFor(() => {
      expect(drawer.querySelector("#sign-in-link-principal_id-problem")?.textContent).toBe("PERSON-PROBLEM-SENTINEL");
    });
    const person = input(drawer, PERSON_LABEL);
    expect(person.getAttribute("aria-invalid")).toBe("true");
    // Described by what the field takes, said before any refusal, and then by the refusal.
    expect(person.getAttribute("aria-describedby")?.split(" ")).toEqual(["sign-in-link-principal_id-hint", "sign-in-link-principal_id-problem"]);
    const account = input(drawer, ACCOUNT_LABEL);
    expect(account.hasAttribute("aria-invalid")).toBe(false);
    expect(account.getAttribute("aria-describedby")).toBe("sign-in-link-subject-hint");
    expect(drawer.querySelector("#sign-in-link-subject-problem")).toBeNull();

    const unmatched = drawer.querySelector(`[aria-label="${WHAT_WAS_NOT_ACCEPTED}"]`);
    expect([...(unmatched?.querySelectorAll("li") ?? [])].map((one) => one.textContent)).toEqual([
      "WHOLE-BODY-SENTINEL",
      "expected_hash NO-INPUT-SENTINEL",
    ]);
    expect(drawer.querySelector(".notice__body > p")?.textContent).toBe("Some of what was sent was not accepted.");
    expect(drawer.querySelector(".notice__trace code")?.textContent).toBe("trace-422");
    expect((document.body.textContent ?? "").split("PERSON-PROBLEM-SENTINEL")).toHaveLength(2);
  });

  test("a write the API accepts draws no problem, marks no input and lists nothing", async () => {
    // What breaks if this is deleted: the sibling that proves the drawing is the refusal's and not
    // the form's. A form that marked its inputs invalid on every answer would pass the test above.
    const { container, drawer } = await linksScreen(() => json({ principal_id: "u_one", outcome: "bound" }));
    // Nothing is marked before anything was refused.
    expect(drawer.querySelector("[aria-invalid]")).toBeNull();

    await link(drawer);

    await waitFor(() => {
      expect(container.textContent).toContain("Linked.");
    });
    expect(document.body.querySelector(".field-problems")).toBeNull();
    expect(document.body.querySelector("[aria-invalid]")).toBeNull();
    expect(document.body.querySelector(`[aria-label="${WHAT_WAS_NOT_ACCEPTED}"]`)).toBeNull();
    expect(document.body.querySelector(".notice__trace")).toBeNull();
  });
});

const SCHEMA: RJSFSchema = {
  type: "object",
  properties: {
    attempts: { type: "integer", title: "Attempts" },
    label: { type: "string", title: "Label" },
    held_back: { type: "string", title: "Held back" },
    rungs: {
      type: "array",
      title: "Rungs",
      items: { type: "object", properties: { attempts: { type: "integer", title: "Rung attempts" } } },
    },
  },
};

const DATA = { attempts: 3, label: "north", rungs: [{ attempts: 1 }] };

function refusal(problems: FieldProblem[]): ApiFailure {
  return {
    status: 422,
    message: "Some of what was sent was not accepted.",
    traceId: "trace-form",
    outcome: "failed",
    problems,
    secondFactorNeeded: false,
  };
}

describe("a generated form", () => {
  test("a validation refusal is drawn in the field's own error slot, and a problem it has no field for is listed", async () => {
    // What breaks if this is deleted: every generated form in the console, the routing rung, the
    // column rule and the grant, back to a refusal with no field named; a nested path landing on the
    // wrong field; or a problem about a withheld field drawn beside its lock, which is a reason drawn
    // beside a lock.
    const { container } = render(
      <SchemaForm
        caption="A rung"
        schema={SCHEMA}
        formData={DATA}
        locked={new Set(["held_back"])}
        failure={refusal([
          { field: "attempts", code: "less_than_equal", message: "ATTEMPTS-SENTINEL" },
          { field: "rungs.0.attempts", code: "greater_than", message: "RUNG-SENTINEL" },
          { field: "held_back", code: "string_too_long", message: "WITHHELD-SENTINEL" },
          { field: "", code: "json_invalid", message: "WHOLE-SENTINEL" },
          { field: "nowhere", code: "extra_forbidden", message: "NOWHERE-SENTINEL" },
        ])}
      />,
    );

    const attempts = container.querySelector("#root_attempts") as HTMLInputElement;
    expect(container.querySelector("#root_attempts__error")?.textContent).toBe("ATTEMPTS-SENTINEL");
    expect(attempts.getAttribute("aria-describedby")).toContain("root_attempts__error");
    await waitFor(() => {
      expect(attempts.getAttribute("aria-invalid")).toBe("true");
    });
    expect(container.querySelector("#root_rungs_0_attempts__error")?.textContent).toBe("RUNG-SENTINEL");
    expect((container.querySelector("#root_label") as HTMLInputElement).hasAttribute("aria-invalid")).toBe(false);

    const unmatched = container.querySelector(`[aria-label="${WHAT_WAS_NOT_ACCEPTED}"]`);
    expect([...(unmatched?.querySelectorAll("li") ?? [])].map((one) => one.textContent)).toEqual([
      "held_back WITHHELD-SENTINEL",
      "WHOLE-SENTINEL",
      "nowhere NOWHERE-SENTINEL",
    ]);
    // Once each: beside the field, and not again in the form's own list of what to check.
    expect((container.textContent ?? "").split("ATTEMPTS-SENTINEL")).toHaveLength(2);
    expect((container.textContent ?? "").split("RUNG-SENTINEL")).toHaveLength(2);
    expect(container.querySelector(".notice__trace code")?.textContent).toBe("trace-form");
  });

  test("a generated form with no failure draws no problem and marks no field", async () => {
    // What breaks if this is deleted: the sibling for the test above. A form whose error slots were
    // filled from something other than the failure, or whose fields were marked invalid on every
    // render, would pass it.
    const { container } = render(
      <SchemaForm caption="A rung" schema={SCHEMA} formData={DATA} locked={new Set(["held_back"])} failure={null} />,
    );
    await waitFor(() => {
      expect(container.querySelector("#root_attempts")).not.toBeNull();
    });
    expect(container.querySelector(".field-problems")).toBeNull();
    expect(container.querySelector("[aria-invalid]")).toBeNull();
    expect(container.querySelector(`[aria-label="${WHAT_WAS_NOT_ACCEPTED}"]`)).toBeNull();
  });
});
