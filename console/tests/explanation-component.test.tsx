/**
 * The one component that explains an act the console cannot offer, in its three forms.
 *
 * `tests/explanations.test.ts` holds the source: where the markup may be written and what every use
 * may name. This holds the behaviour: what is drawn while the words are on their way, once they have
 * arrived, when they could not be read, and when the API sent them with the row. The sentences are the
 * server's registry (`support/explanations.ts`), so a page is compared with a document it did not write.
 *
 * Task ids: M27.15.70
 */

import { fireEvent, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeAll, describe, expect, test } from "vitest";
import { Explanation } from "../src/components/kit";
import { EXPLANATION_NOT_READ } from "../src/components/kit/explanationQuery";
import { loadConsole } from "./support/auth";
import { explanationFor, sentenceFor } from "./support/explanations";
import { json, mountPage, type Answer } from "./support/pageHarness";

const ASKED = "GET /api/v1/console/explanations/";

async function draw(element: () => ReactElement, answers: Record<string, Answer> = {}) {
  return await mountPage(
    "/explained",
    async () => {
      const { createElement } = await import("react");
      return createElement("main", null, createElement("h1", null, "Explained"), element());
    },
    answers,
  );
}

beforeAll(async () => {
  await loadConsole();
}, 60_000);

describe("an act that cannot be done is explained by the server's sentence", () => {
  test("a control is inert, reachable by keyboard, and described by the sentence the API served", async () => {
    // What breaks if this is deleted: a control drawn live over an act that cannot be done, or one that
    // leaves the tab order so a keyboard user never hears why, or a description that is not the server's.
    const { container, sent } = await draw(() => (
      <Explanation form="action" act="agent.level" text="Change" label="Change who can find this agent" />
    ));
    const control = container.querySelector<HTMLButtonElement>("[data-unavailable]");
    expect(control).not.toBeNull();
    expect(control?.getAttribute("aria-disabled")).toBe("true");
    expect(control?.hasAttribute("disabled")).toBe(false);
    expect(control?.getAttribute("data-explains")).toBe("agent.level");
    await waitFor(() => {
      expect(document.getElementById(control?.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
        sentenceFor("agent.level"),
      );
    });
    const before = sent.length;
    fireEvent.click(control as HTMLElement);
    expect(sent.length).toBe(before);
  });

  test("a control is drawn as soon as the page is, whatever sentence is served", async () => {
    // What breaks if this is deleted: the control being drawn only when its sentence is, which moves every
    // control beside it, or being drawn live for the moment between the page and the answer. The words
    // are held back in `useWords` until they arrive, and the control is not.
    const { container } = await draw(
      () => <Explanation form="action" act="agent.level" text="Change" label="Change" />,
      { [`${ASKED}agent.level`]: () => json({ act: "agent.level", form: "action", lead: "", sentence: "x" }) },
    );
    expect(container.querySelector("[data-unavailable]")).not.toBeNull();
  });

  test("a line is the sentence and no control, and a note leads with the lead the server registered", async () => {
    // What breaks if this is deleted: a not-offered sentence drawn as a disabled switch, which says it
    // could be switched on, or a note that forgets whether it is coming soon or not available yet.
    const line = await draw(() => <Explanation form="line" act="role.not_edited" />);
    await waitFor(() => {
      expect(line.container.querySelector('[data-slot="not-offered"]')?.textContent).toBe(sentenceFor("role.not_edited"));
    });
    expect(line.container.querySelector("button")).toBeNull();

    const soon = await draw(() => <Explanation form="note" act="agent.overview" />);
    await waitFor(() => {
      expect(soon.container.querySelector('[data-slot="note"]')?.textContent).toBe(`Coming soon: ${sentenceFor("agent.overview")}`);
    });
    expect(soon.container.querySelector('[data-slot="note"]')?.getAttribute("data-kind")).toBe(explanationFor("agent.overview").lead);

    const not = await draw(() => <Explanation form="note" act="agent.browser" />);
    await waitFor(() => {
      expect(not.container.querySelector('[data-slot="note"]')?.textContent).toBe(`Not available yet: ${sentenceFor("agent.browser")}`);
    });
  });

  test("a sentence the API sent with its row is drawn as sent and asks for nothing", async () => {
    // What breaks if this is deleted: a told sentence being asked for again, so a page whose row already
    // carries its reason makes a second request and can show a different sentence from its own row.
    const told = "This publish is held until a second person approves it.";
    const { container, sent } = await draw(() => (
      <Explanation form="action" told={told} text="Publish" label="Publish" />
    ));
    const control = container.querySelector<HTMLButtonElement>("[data-unavailable]");
    expect(document.getElementById(control?.getAttribute("aria-describedby") ?? "")?.textContent).toBe(told);
    expect(control?.getAttribute("data-explains")).toBe("told");
    expect(sent.filter((one) => one.path.includes("/console/explanations/"))).toEqual([]);
  });

  test("a note told by the API leads with not available yet unless it is told otherwise", async () => {
    // What breaks if this is deleted: a served note drawn with no lead, which reads as a fact about the
    // install and not as something the install cannot yet do.
    const { container } = await draw(() => (
      <>
        <Explanation form="note" told="the vault is not ready." />
        <Explanation form="note" lead="soon" told="a second thing." />
      </>
    ));
    const notes = [...container.querySelectorAll('[data-slot="note"]')].map((one) => one.textContent);
    expect(notes).toEqual(["Not available yet: the vault is not ready.", "Coming soon: a second thing."]);
  });

  test("when the sentence cannot be read the page says so, and an explanation is never left out", async () => {
    // What breaks if this is deleted: a control that cannot be pressed and says nothing about why, which
    // is the thing this component exists to prevent, the day the route is down.
    const failing = { [`${ASKED}agent.level`]: () => json({ message: "down" }, 500), [`${ASKED}role.not_edited`]: () => json({ message: "down" }, 500) };
    const control = await draw(() => <Explanation form="action" act="agent.level" text="Change" label="Change" />, failing);
    await waitFor(() => {
      const mark = control.container.querySelector<HTMLButtonElement>("[data-unavailable]");
      expect(document.getElementById(mark?.getAttribute("aria-describedby") ?? "")?.textContent).toBe(EXPLANATION_NOT_READ);
    });
    const line = await draw(() => <Explanation form="line" act="role.not_edited" />, failing);
    await waitFor(() => {
      expect(line.container.querySelector('[data-slot="not-offered"]')?.textContent).toBe(EXPLANATION_NOT_READ);
    });
  });

  test("an act nobody registered is not read as a sentence", async () => {
    // What breaks if this is deleted: a 404 body being drawn as if it were the explanation, or the
    // sentence of another act.
    const { container } = await draw(() => <Explanation form="line" act="nobody.registered_this" />);
    await waitFor(() => {
      expect(container.querySelector('[data-slot="not-offered"]')?.textContent).toBe(EXPLANATION_NOT_READ);
    });
  });
});
