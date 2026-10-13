/**
 * New automation in the browser: it is written from an agent's Automations section, rehearsed,
 * saved paused, and listed saying when it runs, what it is told, and why it is not running, at a
 * desktop width and at a phone's (M39.9.2.6).
 *
 * **The agent is built through the product's own agent builder**, as the administrator, by the same
 * routes the builder screens call, for the reason `agent-knowledge.spec.ts` gives: the install the
 * harness furnishes has no agent, and a section drawn for an agent a test inserted into a table
 * would prove the page against a row the product never writes. Where the install cannot publish,
 * or the administrator holds no authority to write an automation here, the spec says so and stops
 * rather than passing: a skipped proof is not a proof.
 *
 * **The switch is turned on through the install's own Features route** and turned off again at the
 * end, because New automation ships off and a browser proof that left it on would change what the
 * next spec saw.
 *
 * **What is proved here is the half a browser owns**: the control appears only once the install
 * switched it on, the form is drawn from what the API offered, nothing is written before the
 * second press, the rehearsal shows the earlier triggers with nothing written, the saved automation
 * is on the list with the trigger said in words, a webhook says nothing on this install fires it,
 * and every control is reachable on a phone with nothing scrolling sideways. Which people may and
 * what is stored is `tests/unit/test_acceptance_automation_authoring.py`'s, on the install.
 *
 * **Reached by the menu and the agent's own tabs, never by an address**, as `pages/module.ts`
 * argues. **Not run in the commit that added it**: it needs the full harness (identity provider,
 * install, Chromium), which a development machine without containers cannot start; the browser
 * workflow runs it. Deleting it leaves M39.9.2.6 with only the component tests, which draw the
 * form against answers a test wrote.
 *
 * Task ids: M39.9.2.6
 */

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { checkPage, reset, watch } from "../lib/checklist";
import { signInAsAdmin } from "../lib/signin";
import { openFromMenu } from "../pages/module";

const PHONE = { width: 390, height: 844 } as const;
const DESKTOP = { width: 1280, height: 900 } as const;
const FEATURE = "/api/v1/install/features/automation_authoring";

interface Built {
  readonly agentId: string;
  readonly name: string;
}

interface Draft {
  readonly draft_id: string;
  readonly agent_id: string;
  readonly name: string;
  readonly revision: number;
  readonly document: Record<string, unknown>;
  readonly publish_unavailable: string | null;
}

/** Build an agent through the builder's own routes, or say why this install cannot. */
async function buildAgent(request: APIRequestContext, token: string): Promise<Built | string> {
  const auth = { Authorization: `Bearer ${token}` };
  const started = await request.post("/api/v1/agent-drafts", { headers: auth, data: {} });
  expect(started.status(), "a draft is started").toBe(201);
  const draft = (await started.json()) as Draft;
  if (draft.publish_unavailable !== null) {
    return draft.publish_unavailable;
  }
  const saved = await request.post(`/api/v1/agent-drafts/${draft.draft_id}/revisions`, {
    headers: auth,
    data: { document: draft.document, base: draft.revision },
  });
  expect(saved.status(), "the document is kept").toBe(200);
  const checked = await request.post(`/api/v1/agent-drafts/${draft.draft_id}/check`, { headers: auth, data: { revision: draft.revision } });
  expect(checked.status(), "the draft is checked").toBe(200);
  const result = (await checked.json()) as { passed: boolean; problems: string[] };
  expect(result.problems, "nothing stops the draft being published").toEqual([]);
  const published = await request.post(`/api/v1/agent-drafts/${draft.draft_id}/publish`, {
    headers: auth,
    data: { revision: draft.revision, for_department: false },
  });
  const outcome = (await published.json()) as { state?: string; sentence?: string };
  if (published.status() !== 201 || outcome.state !== "published") {
    return outcome.sentence ?? `publishing answered ${String(published.status())}`;
  }
  return { agentId: draft.agent_id, name: draft.name };
}

async function openAutomations(page: Page, agent: Built): Promise<void> {
  await openFromMenu(page, "/agents", "Agents");
  await page.getByRole("link", { name: agent.name }).first().click();
  await page.locator(`a[href="/agents/${agent.agentId}/automations"]`).first().click();
  await expect(page.getByText("What this agent does on a schedule")).toBeVisible({ timeout: 20_000 });
}

/** Whether nothing on the page is wider than the window, which is a phone's horizontal scroll. */
async function fitsTheWindow(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
}

test("New automation is written, rehearsed and saved paused from an agent's page, at desktop and phone widths", async ({ browser, request }, info) => {
  const page = await browser.newPage({ viewport: DESKTOP });
  const seen = watch(page);
  const token = await signInAsAdmin(page);
  const auth = { Authorization: `Bearer ${token}` };
  await expect(page.locator('nav[aria-label="Sections"]')).toBeVisible({ timeout: 30_000 });

  const built = await buildAgent(request, token);
  test.skip(typeof built === "string", `this install cannot build an agent through the builder: ${String(built)}`);
  const agent = built as Built;

  // Off, as an install ships it: the section offers no New automation.
  await openAutomations(page, agent);
  await expect(page.getByRole("button", { name: "New automation" })).toHaveCount(0);

  const switched = await request.post(FEATURE, { headers: auth, data: { on: true } });
  expect(switched.status(), "the administrator may switch the feature on").toBe(200);
  try {
    const options = await request.get(`/api/v1/agents/${agent.agentId}/automation-authoring`, { headers: auth });
    test.skip(options.status() !== 200, "the administrator holds no authority to write an automation on this agent");

    // Reload the section through the menu so the options are asked for again.
    await openFromMenu(page, "/agents", "Agents");
    await page.getByRole("link", { name: agent.name }).first().click();
    await page.locator(`a[href="/agents/${agent.agentId}/automations"]`).first().click();
    await checkPage(page, seen, "An agent's Automations section with New automation", info);
    reset(seen);
    const section = page.locator('[data-slot="new-automation"]');
    await expect(section.getByRole("button", { name: "New automation" })).toBeVisible({ timeout: 20_000 });
    await section.getByRole("button", { name: "New automation" }).click();

    // Start from a named outcome, change when it runs, and review: nothing is written yet.
    const form = section.locator('[data-slot="authoring"] form');
    await form.locator('[name="start"]').selectOption({ index: 1 });
    await form.locator('[name="every"]').selectOption("day");
    await form.locator('[name="hour"]').selectOption("6");
    await form.getByRole("button", { name: "Review and rehearse" }).click();
    const rehearsal = section.locator('[data-slot="authoring-rehearsal"]');
    await expect(rehearsal).toBeVisible({ timeout: 30_000 });
    await expect(rehearsal.locator("li")).toHaveCount(3);
    await expect(rehearsal).toContainText("Nothing was read, written or sent");
    const before = await request.get(`/api/v1/agents/${agent.agentId}/automations`, { headers: auth });
    expect(((await before.json()) as { items: unknown[] }).items, "reviewing wrote nothing").toHaveLength(0);

    // Save it: it is listed, paused, with its trigger said in words.
    await section.getByRole("button", { name: "Save it paused" }).click();
    await expect(section.getByText("Saved")).toBeVisible({ timeout: 30_000 });
    const card = page.locator('[data-slot="authored-card"]').first();
    await expect(card).toContainText("Runs every day at 06:00 UTC", { timeout: 30_000 });
    await expect(card).toContainText("Writes");

    // A webhook can be written and says on its card that nothing on this install fires it.
    await section.getByRole("button", { name: "New automation" }).click();
    await form.locator('[name="start"]').selectOption({ index: 1 });
    await form.locator('[name="trigger"]').selectOption("webhook");
    await form.locator('[name="endpoint"]').fill("browser_check");
    await form.getByRole("button", { name: "Review and rehearse" }).click();
    await expect(section.getByText("Nothing on this install fires this yet").first()).toBeVisible({ timeout: 30_000 });
    await section.getByRole("button", { name: "Save it paused" }).click();
    await expect(page.getByText("Runs when browser check is called from outside")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Nothing on this install fires this yet").first()).toBeVisible();
    expect(seen.refusedByPolicy, "nothing was refused under the page's policy").toEqual([]);

    // The same section at a phone's width: every control reachable, nothing scrolling sideways.
    await page.setViewportSize(PHONE);
    await expect(page.locator('[data-slot="authored-card"]').first()).toBeVisible();
    expect(await fitsTheWindow(page), "the section fits a phone's width").toBe(true);
    await section.getByRole("button", { name: "New automation" }).click();
    expect(await fitsTheWindow(page), "the form fits a phone's width").toBe(true);
    const box = await form.getByRole("button", { name: "Review and rehearse" }).boundingBox();
    expect(box?.height ?? 0, "a control is large enough to press on a phone").toBeGreaterThanOrEqual(40);
  } finally {
    await request.post(FEATURE, { headers: auth, data: { on: false } });
    await page.close();
  }
});
