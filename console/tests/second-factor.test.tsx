/**
 * A sign-in without a second factor is said in the API's words, decided by the API's flag, and
 * answered by a sign-in that makes the identity provider ask again.
 *
 * The staging install on 2026-09-17 had a person signed in without their second factor whose
 * administration was refused, correctly, with the 404 every refusal is. The console drew "I could
 * not find that." for work they held, and nothing on the screen said what to do. Three things
 * follow and each is held here with its sibling.
 *
 * **A failure asking for a second factor shows the API's sentence and a way to sign in again, and
 * the same 404 without the flag shows neither.** Mounted on My workspace, the one screen that words
 * a 404 itself, so the proof that nothing branches on the status is the screen most tempted to.
 * `tests/screen-states.test.tsx` holds every other registered address to the first half.
 *
 * **The shell says so before anything fails**, from `GET /me`'s own flag, and says nothing at
 * `strong` or whenever the flag is false.
 *
 * **Signing in again sends `prompt=login`, and an ordinary sign-in does not**, which is
 * `auth/session.A_STRONGER_SIGN_IN_HAS_TO_ASK_AGAIN`.
 *
 * Task ids: M27.9.2
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_FOUND_MESSAGE, failureFrom } from "../src/api/errors";
import {
  ADMINISTRATION_NEEDS_A_SECOND_FACTOR,
  THIS_SIGN_IN_HAS_NO_SECOND_FACTOR,
  VERB_WORDS,
  readSignInStrength,
  verbsInWords,
} from "../src/layout/signInStrengthQuery";
import { OPENS_ON_THE_MEMBER_GRANT, READING_WORKSPACE } from "../src/pages/MyWorkspace";
import { A_SECOND_FACTOR_IS_NEEDED } from "../src/ui/FailureNotice";
import { SIGN_IN_AGAIN_WITH_YOUR_AUTHENTICATOR } from "../src/ui/SignInAgain";
import { AUTHORIZATION_ENDPOINT, fakeIdentityProvider, loadConsole, signIn, type LoadedConsole } from "./support/auth";
import { answerNavigation } from "./support/navigation";
import { readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const WORKSPACE_OPERATION = "/api/v1/me/workspace";
const ME_OPERATION = "/api/v1/me";
const SECOND_FACTOR_SENTENCE =
  "Administration and approvals need a sign-in with a second factor, and this sign-in has none. " +
  "SENTINEL-FROM-THE-API";

beforeAll(async () => {
  await import("../src/pages/MyWorkspace");
  await import("../src/App");
}, 60_000);

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

function refusal(secondFactorNeeded: boolean): Response {
  return json(
    {
      message: secondFactorNeeded ? SECOND_FACTOR_SENTENCE : NOT_FOUND_MESSAGE,
      trace_id: "trace-refused",
      problems: [],
      second_factor_needed: secondFactorNeeded,
    },
    404,
    { "x-trace-id": "trace-refused" },
  );
}

async function workspaceRefused(secondFactorNeeded: boolean): Promise<{ container: HTMLElement; loaded: LoadedConsole }> {
  const idp = fakeIdentityProvider({
    api(url) {
      return new URL(url, CONSOLE_ORIGIN).pathname === WORKSPACE_OPERATION ? refusal(secondFactorNeeded) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { MyWorkspace } = await import("../src/pages/MyWorkspace");
  const router = createMemoryRouter([{ path: "/me", element: <MyWorkspace /> }], { initialEntries: ["/me"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_WORKSPACE) || container.querySelector(".notice") === null) {
      throw new Error("still reading");
    }
  });
  return { container, loaded };
}

function signInAgain(container: HTMLElement): HTMLButtonElement | undefined {
  return [...container.querySelectorAll("button")].find(
    (one) => one.textContent === SIGN_IN_AGAIN_WITH_YOUR_AUTHENTICATOR,
  );
}

describe("a failure that asks for a second factor", () => {
  test("a screen refused for a sign-in with no second factor shows the API's sentence and a way to sign in again", async () => {
    // What breaks if this is deleted: "I could not find that." for work the person holds, with the
    // member grant note under it sending them to ask for a grant they already have, and no control
    // to do the one thing that would help.
    const { container } = await workspaceRefused(true);

    expect(container.querySelector(".notice__title")?.textContent).toBe(A_SECOND_FACTOR_IS_NEEDED);
    expect(container.querySelector(".notice__body > p")?.textContent).toBe(SECOND_FACTOR_SENTENCE);
    expect(container.textContent).not.toContain(NOT_FOUND_MESSAGE);
    expect(container.textContent).not.toContain(OPENS_ON_THE_MEMBER_GRANT);
    expect(signInAgain(container)).toBeDefined();
    expect(container.querySelector(".notice__trace code")?.textContent).toBe("trace-refused");
  });

  test("the same 404 without the flag is the ordinary refusal and offers no second factor", async () => {
    // What breaks if this is deleted: the proof that nothing chooses the control from the status. A
    // console that offered to sign in again on every 404 would pass the test above, and would tell
    // every person looking at a record they may not see that a second factor would show it to them,
    // which is the difference between DENIED and ABSENT said in a helpful voice.
    const { container } = await workspaceRefused(false);

    expect(container.querySelector(".notice__title")?.textContent).not.toBe(A_SECOND_FACTOR_IS_NEEDED);
    expect(container.querySelector(".notice__body > p")?.textContent).toBe(NOT_FOUND_MESSAGE);
    expect(container.textContent).toContain(OPENS_ON_THE_MEMBER_GRANT);
    expect(signInAgain(container)).toBeUndefined();
  });

  test("the flag is read from the body as exactly true and never from the status or the outcome", () => {
    // What breaks if this is deleted: a hand-built document whose flag is the string "false" sending a
    // person round a sign-in, or a flag inferred from a 404 or from "denied", which is every record
    // this reader may not see.
    const response = (status: number) => new Response(null, { status });
    expect(failureFrom(response(404), { message: "x", second_factor_needed: true }).secondFactorNeeded).toBe(true);
    expect(failureFrom(response(500), { message: "x", second_factor_needed: true }).secondFactorNeeded).toBe(true);
    expect(failureFrom(response(404), { message: "x", second_factor_needed: "true" }).secondFactorNeeded).toBe(false);
    expect(failureFrom(response(404), { message: "x", outcome: "denied" }).secondFactorNeeded).toBe(false);
    expect(failureFrom(response(404), null).secondFactorNeeded).toBe(false);
  });
});

describe("signing in again", () => {
  test("the control starts a sign-in that asks the identity provider to authenticate again", async () => {
    // What breaks if this is deleted: a button that sends the person to the identity provider, which
    // answers from the session that had no second factor, so they land where they started and the
    // button appears to do nothing.
    const { container, loaded } = await workspaceRefused(true);
    const before = loaded.location.assign.mock.calls.length;

    fireEvent.click(signInAgain(container) as HTMLButtonElement);

    await waitFor(() => {
      expect(loaded.location.assign.mock.calls.length).toBe(before + 1);
    });
    const url = loaded.location.lastAssigned();
    expect(`${url.origin}${url.pathname}`).toBe(AUTHORIZATION_ENDPOINT);
    expect(url.searchParams.get("prompt")).toBe("login");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  });

  test("an ordinary sign-in does not ask the identity provider to authenticate again", async () => {
    // What breaks if this is deleted: `prompt=login` on every sign-in, which turns every reload and
    // every expired token into a password prompt, and is the sibling that proves the parameter is
    // the control's and not the flow's.
    const loaded = await loadConsole();
    await signIn(loaded);
    const first = new URL(String(loaded.location.assign.mock.calls[0]?.[0]), CONSOLE_ORIGIN);
    expect(`${first.origin}${first.pathname}`).toBe(AUTHORIZATION_ENDPOINT);
    expect(first.searchParams.has("prompt")).toBe(false);
  });
});

async function shellWith(me: unknown): Promise<{ container: HTMLElement; loaded: LoadedConsole }> {
  const idp = fakeIdentityProvider({
    api(url) {
      const navigation = answerNavigation(url);
      if (navigation) {
        return navigation;
      }
      return new URL(url, CONSOLE_ORIGIN).pathname === ME_OPERATION ? json(me) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  // The ask screen asks nothing on arrival, so the only read of `/me` is the shell's.
  const router = createMemoryRouter(routes, { initialEntries: ["/ask"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    expect(container.querySelector("h1")).not.toBeNull();
    expect(loaded.idp.urls.some((one) => new URL(one, CONSOLE_ORIGIN).pathname === ME_OPERATION)).toBe(true);
  });
  // Every answer the stand-in gives settles within the timers after it.
  for (let turn = 0; turn < 3; turn += 1) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  return { container, loaded };
}

const CALLER = {
  principal_id: "u_admin",
  display_name: "An administrator",
  channel: "web",
  ent_hash: "f".repeat(64),
};

describe("the shell's banner", () => {
  test("a sign-in the API says needs a second factor gets a banner naming what is withheld and a way to sign in again", async () => {
    // What breaks if this is deleted: a person signed in without their second factor finding out only
    // when a screen refuses them, in the words every refusal uses.
    const { container, loaded } = await shellWith({
      ...CALLER,
      assurance: "authenticated",
      withheld_verbs: ["admin", "approve"],
      second_factor_needed: true,
    });

    const banner = container.querySelector(".shell__banner");
    expect(banner?.querySelector(".notice__title")?.textContent).toBe(THIS_SIGN_IN_HAS_NO_SECOND_FACTOR);
    expect(banner?.textContent).toContain(ADMINISTRATION_NEEDS_A_SECOND_FACTOR);
    expect(banner?.textContent).toContain("administration and approvals");
    // Outside the page, so it is the frame's and never one of a page's own states.
    expect(container.querySelector("main#main .shell__banner")).toBeNull();

    const before = loaded.location.assign.mock.calls.length;
    fireEvent.click(signInAgain(banner as HTMLElement) as HTMLButtonElement);
    await waitFor(() => {
      expect(loaded.location.assign.mock.calls.length).toBe(before + 1);
    });
    expect(loaded.location.lastAssigned().searchParams.get("prompt")).toBe("login");
  });

  test("a strong sign-in with nothing withheld gets no banner", async () => {
    // What breaks if this is deleted: the sibling for the test above. A banner drawn on every page
    // for every person would pass it, and would teach everybody to ignore it.
    const { container } = await shellWith({
      ...CALLER,
      assurance: "strong",
      withheld_verbs: [],
      second_factor_needed: false,
    });

    expect(container.querySelector(".shell__banner")).toBeNull();
    expect(container.textContent).not.toContain(THIS_SIGN_IN_HAS_NO_SECOND_FACTOR);
    expect(signInAgain(container)).toBeUndefined();
  });

  test("the banner is the flag's and not the assurance word's", async () => {
    // What breaks if this is deleted: a banner inferred from `assurance`, which sends a person who
    // holds nothing a second factor would restore round a sign-in that changes nothing.
    const { container } = await shellWith({
      ...CALLER,
      assurance: "authenticated",
      withheld_verbs: [],
      second_factor_needed: false,
    });

    expect(container.querySelector(".shell__banner")).toBeNull();
  });

  test("every verb a grant can carry has words, and a body without the fields withholds nothing", () => {
    // What breaks if this is deleted: a verb added to `brain.core.entitlement.VERBS` named on the
    // banner as its code, or an older API's `/me`, which carries neither field, drawing a banner.
    const python = readRepoFile("src/brain/core/entitlement.py");
    const declared = /^VERBS = frozenset\(\{([^}]*)\}\)$/m.exec(python)?.[1] ?? "";
    const verbs = [...declared.matchAll(/"([a-z_]+)"/g)].map((one) => one[1]).sort();
    expect(verbs.length).toBeGreaterThan(0);
    expect(Object.keys(VERB_WORDS).sort()).toEqual(verbs);

    expect(readSignInStrength({ ...CALLER, assurance: "strong" })).toEqual({ secondFactorNeeded: false, withheldVerbs: [] });
    expect(readSignInStrength({ second_factor_needed: "true", withheld_verbs: ["admin"] }).secondFactorNeeded).toBe(false);
    expect(verbsInWords(["admin"])).toBe("administration");
    expect(verbsInWords(["read", "approve", "admin"])).toBe("reading, approvals and administration");
    expect(verbsInWords(["something_new"])).toBe("something_new");
  });
});
