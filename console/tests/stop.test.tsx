/**
 * The Stop control in the header and the Stop screen (M27.15.14, M27.12.4, M27.2.8).
 *
 * **Driven through the application's own route table**, signed in through the real session modules,
 * against a stand-in API answering the menu, `GET /api/v1/halts` and the two writes with the bodies
 * their routes declare. The control is drawn from the menu's offer and stops in one press with no
 * words; the screen resumes only with a reason and a confirmation, and says when the stops cannot be
 * read. The two sentences copied from Python are read back out of it.
 *
 * Task ids: M27.15.14, M27.12.4, M27.2.8
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { ASK_ADDRESS } from "../src/pages/Ask";
import {
  CANNOT_TELL,
  HALTS_API_PATH,
  MINIMUM_REASON,
  NOT_ASKED_YET_LEAD,
  RESUME_API_PATH,
  RESUME_LABEL,
  SAY_WHY,
  STOP_EVERYTHING,
  STOP_PATH,
  STOPPED_FROM_THE_CONSOLE,
  STOPPED_STATUS,
} from "../src/pages/stopQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, departmentConsole } from "./support/navigation";
import { readRepoFile } from "./support/repo";

const ORIGIN = "https://console.test";
const API = "/api/v1";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

interface Sent {
  readonly path: string;
  readonly body: unknown;
}

function halts(known = true, halted = true): unknown {
  return {
    known,
    halts: halted
      ? [{ scope: "department", target: "web", declared_by: "u_admin", at: "2019-03-06T09:00:00Z", reason: STOPPED_FROM_THE_CONSOLE }]
      : [],
    gaps: [],
    not_asked_yet: ["agent"],
    may_stop_everything: true,
  };
}

async function opened(path: string, menu: unknown, list: unknown = halts()): Promise<{ container: HTMLElement; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const address = new URL(url, ORIGIN);
      if (init?.method === "POST") {
        sent.push({ path: address.pathname, body: typeof init.body === "string" ? JSON.parse(init.body) : null });
        if (address.pathname === `${API}${RESUME_API_PATH}`) {
          return json({ said: "u_owner restarted work u_admin had stopped: department (web). The cause was fixed.", overrides_somebody_else: true });
        }
        if (address.pathname === `${API}${HALTS_API_PATH}`) {
          return json({ scope: "everything", target: "", declared_by: "u_owner", at: "2019-03-06T09:00:00Z", reason: STOPPED_FROM_THE_CONSOLE }, 201);
        }
      }
      if (address.pathname === `${API}/console/navigation`) {
        return json(menu);
      }
      if (address.pathname === `${API}${HALTS_API_PATH}`) {
        return json(list);
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp, path });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, sent };
}

function stopButton(container: HTMLElement): HTMLButtonElement | null {
  return container.querySelector<HTMLButtonElement>('[data-slot="stop-control"] button');
}

async function control(container: HTMLElement): Promise<HTMLButtonElement> {
  await waitFor(() => {
    if (stopButton(container) === null) {
      throw new Error("the Stop control has not arrived");
    }
  });
  return stopButton(container)!;
}

describe("the Stop control in the header", () => {
  test("one press stops everything for a reader whose stop reaches it, with no words and no confirmation", async () => {
    // What breaks if this is deleted: a control that asks to be sure, or makes somebody type,
    // at the moment the owner's rule says it must simply stop.
    const { container, sent } = await opened(ASK_ADDRESS, { ...COMPANY_CONSOLE, stop: "everything" });
    const button = await control(container);
    expect(button.getAttribute("aria-label")).toBe(STOP_EVERYTHING);
    fireEvent.click(button);

    await waitFor(() => {
      if (!container.textContent?.includes(STOPPED_STATUS)) {
        throw new Error("the press was not said");
      }
    });
    expect(sent).toEqual([{ path: `${API}${HALTS_API_PATH}`, body: { scope: "everything", target: "" } }]);
    expect(container.querySelector('[role="dialog"], [role="alertdialog"]')).toBeNull();
    expect(container.querySelector(`[data-slot="stop-control"] a[href="${STOP_PATH}"]`)?.textContent).toBe(STOPPED_STATUS);
  });

  test("a department administrator's press stops their department and nothing wider", async () => {
    // What breaks if this is deleted: the department console's press can send a stop on
    // everything, which the API refuses, so a department administrator's stop stops nothing.
    const { container, sent } = await opened(ASK_ADDRESS, { ...departmentConsole("web"), stop: "departments" });
    fireEvent.click(await control(container));

    await waitFor(() => {
      if (sent.length === 0) {
        throw new Error("nothing was sent");
      }
    });
    expect(sent).toEqual([{ path: `${API}${HALTS_API_PATH}`, body: { scope: "department", target: "web" } }]);
  });

  test("a reader the menu offers no stop is drawn no control", async () => {
    // What breaks if this is deleted: a control drawn for everybody, which the API refuses on
    // every press and which reads as the console offering a stop it does not have.
    const { container } = await opened(ASK_ADDRESS, { ...COMPANY_CONSOLE, stop: "" });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(container.querySelector('[data-slot="stop-control"]')).toBeNull();
  });
});

describe("the Stop screen", () => {
  test("a resume is refused without a reason, then confirmed, and says whose stop it lifted", async () => {
    // What breaks if this is deleted: a resume sent with no reason, or one press away from
    // restarting what somebody else stopped.
    const { container, sent } = await opened(STOP_PATH, COMPANY_CONSOLE);
    await waitFor(() => {
      if (container.querySelector(`form[aria-label^="${RESUME_LABEL}"]`) === null) {
        throw new Error("the resume form has not arrived");
      }
    });
    const form = container.querySelector<HTMLFormElement>(`form[aria-label^="${RESUME_LABEL}"]`)!;
    fireEvent.submit(form);
    await waitFor(() => {
      if (!form.textContent?.includes(SAY_WHY)) {
        throw new Error("the missing reason was not said");
      }
    });
    expect(sent).toEqual([]);

    fireEvent.change(form.querySelector("input")!, { target: { value: "The cause was fixed." } });
    fireEvent.submit(form);
    const confirm = await waitFor(() => {
      const found = [...document.querySelectorAll("button")].find((one) => one.textContent === RESUME_LABEL && one.closest('[role="alertdialog"], [role="dialog"]') !== null);
      if (found === undefined) {
        throw new Error("the confirmation has not opened");
      }
      return found;
    });
    expect(sent).toEqual([]);
    fireEvent.click(confirm);

    await waitFor(() => {
      if (!container.textContent?.includes("restarted work u_admin had stopped")) {
        throw new Error("the resume was not said");
      }
    });
    expect(sent).toEqual([{ path: `${API}${RESUME_API_PATH}`, body: { scope: "department", target: "web", reason: "The cause was fixed." } }]);
  });

  test("stops that cannot be read are said, and the axis nothing asks is named rather than offered", async () => {
    // What breaks if this is deleted: an unreadable store drawn as nothing stopped while every
    // request is refused, or an agent offered as stoppable when stopping it stops nothing.
    const { container } = await opened(STOP_PATH, COMPANY_CONSOLE, halts(false, false));
    await waitFor(() => {
      if (!container.textContent?.includes(CANNOT_TELL)) {
        throw new Error("the unreadable state was not said");
      }
    });
    expect(container.textContent).toContain(NOT_ASKED_YET_LEAD);
    const offered = [...container.querySelectorAll("option")].map((one) => one.getAttribute("value"));
    expect(offered).not.toContain("agent");
    expect(offered).toContain("everything");
  });

  test("the two sentences copied from Python are the ones Python holds", () => {
    // What breaks if this is deleted: the console's copy of the stored sentence or of the reason's
    // floor drifts from the API's, and the page promises a length the API refuses.
    const store = readRepoFile("src/brain/ops/halt_store.py");
    const domain = readRepoFile("src/brain/ops/halt.py");
    expect(/^STOPPED_FROM_THE_CONSOLE: Final = "([^"]+)"$/m.exec(store)?.[1]).toBe(STOPPED_FROM_THE_CONSOLE);
    expect(Number(/^MINIMUM_REASON = (\d+)$/m.exec(domain)?.[1])).toBe(MINIMUM_REASON);
  });
});
