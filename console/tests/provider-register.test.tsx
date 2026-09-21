/**
 * The provider register on the Models screen and an agent's pinned model on its profile.
 *
 * Driven through the real route table with the page cases' stand-in answers, each overridden where
 * the register or the pin is what is under test.
 *
 * Task ids: M5.6.4, M5.7.2, M5.7.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ADD_PROVIDER, REGISTER_HEADING } from "../src/pages/providerRegisterQuery";
import { MODEL_HEADING, PIN_MODEL } from "../src/pages/agentModelPinQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { PAGES } from "./support/pageCases";

beforeAll(async () => {
  await import("../src/pages/Models");
}, 60_000);

const KEY = "sk-PASTED-KEY-NEVER-DRAWN-0123456789";

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}

const PROVIDERS = {
  profile: "hosted",
  providers: [
    {
      provider: "anthropic",
      description: "Claude",
      hosted: true,
      switched_on: true,
      switched_by: null,
      switched_at: null,
      key_held: true,
      credential: null,
      registered: {
        label: "Claude",
        kind: "builtin",
        base_url: null,
        models: [],
        processing_region: "eu-west-1",
        residency_class: "region_pinned",
        storage_location: "Ireland",
        retention_terms: "Zero retention",
        training_terms: "Not used for training",
        agreement_url: "https://contracts.example.test/dpa.pdf",
        lane_overrides: [{ lane: "answer", timeout_seconds: 10, attempts: null }],
      },
      disclosed: [{ category: "question", told: "Questions people asked", attempts: 7 }],
    },
  ],
  rungs: [],
  exhausted_tiers: [],
  editable: true,
  vault: null,
  vault_told: null,
};

async function mounted(path: string, answers: Record<string, unknown>): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      const pathname = new URL(url, "https://console.test").pathname;
      return pathname in answers ? json(answers[pathname]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  return { container, idp };
}

function writes(idp: FakeIdp): { method: string; body: unknown }[] {
  return idp.calls
    .filter((call) => String(call.url).includes("/api/v1/") && (call.init?.method ?? "GET") !== "GET")
    .map((call) => ({
      method: call.init?.method ?? "GET",
      body: typeof call.init?.body === "string" ? (JSON.parse(call.init.body) as unknown) : null,
    }));
}

describe("the provider register", () => {
  test("each provider is drawn with its terms and what it has been sent, with the count", async () => {
    // What breaks if this is deleted: the register is stored and exported and never shown, so an
    // administrator cannot see what left for where without downloading a file.
    const { container } = await mounted("/models", {
      ...PAGES["/models"]?.answers,
      "/api/v1/models/providers": PROVIDERS,
    });
    await waitFor(() => {
      if (!container.textContent?.includes(REGISTER_HEADING) || !container.textContent.includes("Zero retention")) {
        throw new Error("the register has not arrived");
      }
    });

    const text = container.textContent ?? "";
    expect(text).toContain("eu-west-1 (region pinned)");
    expect(text).toContain("Not used for training");
    expect(text).toContain("Questions people asked: 7 calls");
    expect(container.querySelector('a[href="https://contracts.example.test/dpa.pdf"]')).not.toBeNull();
  });

  test("a provider is added only from its confirmation, and its key is sent once and left nowhere", async () => {
    // What breaks if this is deleted: the key reaches the API from an unconfirmed press, or stays
    // in the form, or is drawn back, any of which puts a provider key on a screen.
    const { container, idp } = await mounted("/models", {
      ...PAGES["/models"]?.answers,
      "/api/v1/models/providers": PROVIDERS,
    });
    await waitFor(() => {
      if (!container.querySelector(`form[aria-label="Add an OpenAI-compatible provider"]`)) {
        throw new Error("the add form has not arrived");
      }
    });
    const form = container.querySelector(`form[aria-label="Add an OpenAI-compatible provider"]`) as HTMLFormElement;
    const field = (name: string) => form.querySelector(`[name="${name}"]`) as HTMLElement;
    fireEvent.change(field("slug"), { target: { value: "acme_llm" } });
    fireEvent.change(field("label"), { target: { value: "Acme LLM" } });
    fireEvent.change(field("base_url"), { target: { value: "https://llm.example.test/v1" } });
    fireEvent.change(field("models"), { target: { value: "acme-large\nacme-small" } });
    fireEvent.change(field("key"), { target: { value: KEY } });
    fireEvent.submit(form);
    expect(writes(idp)).toEqual([]);

    const confirm = [...container.querySelectorAll("button")].filter((one) => one.textContent === ADD_PROVIDER);
    fireEvent.click(confirm[0] as HTMLElement);
    await waitFor(() => {
      if (writes(idp).length === 0) {
        throw new Error("nothing sent");
      }
    });

    expect(writes(idp)).toEqual([
      {
        method: "POST",
        body: {
          slug: "acme_llm",
          label: "Acme LLM",
          base_url: "https://llm.example.test/v1",
          models: ["acme-large", "acme-small"],
          key: KEY,
        },
      },
    ]);
    await waitFor(() => {
      if ((field("key") as HTMLInputElement).value !== "") {
        throw new Error("the key is still in the form");
      }
    });
    expect(container.innerHTML).not.toContain(KEY);
  });
});

describe("an agent's pinned model", () => {
  test("the profile says the tier and pins a model only from the confirmation", async () => {
    // What breaks if this is deleted: M5.7.3's pin has no way in from the console, or is sent from
    // an unconfirmed press that moves every question to the agent.
    const { container, idp } = await mounted("/agents/quote-helper", {
      ...PAGES["/agents/:agentId"]?.answers,
    });
    await waitFor(() => {
      const profile = [...container.querySelectorAll("button")].find((one) => one.textContent === "Profile");
      if (profile === undefined) {
        throw new Error("the workspace has not arrived");
      }
      fireEvent.click(profile);
    });
    await waitFor(() => {
      if (!container.textContent?.includes(MODEL_HEADING)) {
        throw new Error("the profile has not opened");
      }
    });
    expect(container.textContent).toContain("This agent uses the main tier's chain.");

    const form = container.querySelector('form[aria-label="Pin a model for this agent"]') as HTMLFormElement;
    fireEvent.change(form.querySelector('[name="provider"]') as HTMLElement, { target: { value: "moonshot" } });
    fireEvent.change(form.querySelector('[name="model"]') as HTMLElement, { target: { value: "kimi-k2" } });
    fireEvent.submit(form);
    expect(writes(idp)).toEqual([]);
    const confirm = [...container.querySelectorAll("button")].filter((one) => one.textContent === PIN_MODEL);
    fireEvent.click(confirm[0] as HTMLElement);
    await waitFor(() => {
      if (writes(idp).length === 0) {
        throw new Error("nothing sent");
      }
    });

    expect(writes(idp)).toEqual([{ method: "PUT", body: { provider: "moonshot", model: "kimi-k2" } }]);
  });
});
