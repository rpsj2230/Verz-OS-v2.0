/**
 * First run's logo upload: a file chosen on the company screen reaches the server with the setup
 * code, a refusal is the server's sentence, and nothing about the file becomes an answer.
 *
 * **Driven through the real first run**, the way `first-run-staff-list.test.tsx` is, with the upload
 * route answered by a stand-in that records what was sent. The copies are checked against the
 * originals: the route's address is read out of the Python module that serves it, the body against
 * the API document, and the size limit against `brain.branding.MAX_LOGO_BYTES`.
 *
 * Task ids: M42.5.5
 */

import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import { APPOINTMENT_PATH, FIRST_RUN_PATH, SETUP_REFUSED_MESSAGE } from "../src/setup/wizard";
import { LOGO_UPLOAD_PATH, MAX_LOGO_BYTES, TOO_LARGE, base64Of, logoBody } from "../src/setup/logo";
import { LOGO_KEPT, LOGO_NOT_KEPT_TITLE } from "../src/components/LogoUpload";
import { CONSOLE_ORIGIN, fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { declaredPropertyNames, declaredRequestBodySchema } from "./support/openapi";
import { extractOne, readRepoFile } from "./support/repo";

const CODE = `CODE-SENTINEL-${"c".repeat(50)}`;
const FILE_ID = "first-run-company-logo-file";

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", "x-trace-id": "TRACE-SENTINEL" },
  });
}

interface Seen {
  readonly path: string;
  readonly body: unknown;
}

function standIn(upload: () => Response) {
  const seen: Seen[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      if (path === LOGO_UPLOAD_PATH || path === APPOINTMENT_PATH) {
        seen.push({ path, body: init?.body === undefined ? null : JSON.parse(String(init.body)) });
      }
      if (path === LOGO_UPLOAD_PATH) {
        return upload();
      }
      return null;
    },
  });
  return { idp, seen };
}

function headingOf(container: HTMLElement): string {
  return container.querySelector("h1")?.textContent ?? "";
}

function give(container: HTMLElement, id: string, value: string): void {
  const found = container.querySelector(`#${id}`);
  if (!found) {
    throw new Error(`No control #${id} on "${headingOf(container)}".`);
  }
  fireEvent.input(found, { target: { value } });
  fireEvent.change(found, { target: { value } });
}

function press(container: HTMLElement, text: string): void {
  const button = [...container.querySelectorAll("button")].find((one) => one.textContent === text);
  if (!button) {
    throw new Error(`No button "${text}" on "${headingOf(container)}".`);
  }
  if (button.type === "submit" && button.form) {
    fireEvent.submit(button.form);
    return;
  }
  fireEvent.click(button);
}

async function arriveAt(container: HTMLElement, title: string): Promise<void> {
  await waitFor(() => expect(headingOf(container)).toBe(title));
}

async function openAtTheCompany(idp: ReturnType<typeof fakeIdentityProvider>) {
  const loaded = await loadConsole({ idp, path: FIRST_RUN_PATH });
  const landed = await signIn(loaded, { returnTo: FIRST_RUN_PATH });
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [landed] });
  const { container } = render(<RouterProvider router={router} />);
  await arriveAt(container, "Enter the setup code");
  give(container, "first-run-setup_code-setup_code", CODE);
  press(container, "Continue");
  await arriveAt(container, "Your company");
  return { container };
}

function choose(container: HTMLElement, file: File): void {
  const input = container.querySelector<HTMLInputElement>(`#${FILE_ID}`);
  if (!input) {
    throw new Error("No logo chooser on the company screen.");
  }
  fireEvent.change(input, { target: { files: [file] } });
}

const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3]);
const png = () => new File([PNG_BYTES], "mark.png", { type: "image/png" });

beforeAll(async () => {
  await import("../src/App");
}, 60_000);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the upload's copies of the server", () => {
  test("the address, the limit and the body are the ones the server has", () => {
    // What breaks if this is deleted: a route renamed on the server and not here, so every logo
    // posts to nothing and is drawn as the setup refusal; or a limit that parts company with it.
    const routes = readRepoFile("src/brain/logo_routes.py");
    const branding = readRepoFile("src/brain/branding.py");
    expect(LOGO_UPLOAD_PATH).toBe(extractOne(routes, /^UPLOAD_PATH: Final = "([^"]+)"$/m, "UPLOAD_PATH"));
    expect(MAX_LOGO_BYTES).toBe(
      Number(
        extractOne(branding, /^MAX_LOGO_BYTES: Final = (\d+) \* 1024$/m, "MAX_LOGO_BYTES"),
      ) * 1024,
    );
    expect(declaredPropertyNames(declaredRequestBodySchema(LOGO_UPLOAD_PATH, "post"))).toEqual(
      ["image", "setup_code"],
    );
  });

  test("a file is sent as the bytes it holds in base64 beside the setup code and nothing else", async () => {
    // What breaks if this is deleted: a body the route forbids (it forbids extra keys), or bytes
    // mangled on the way, which the server would refuse as not an image.
    expect(await base64Of(new Blob([PNG_BYTES]))).toBe(btoa(String.fromCharCode(...PNG_BYTES)));
    expect(Object.keys(await logoBody("code", new Blob([PNG_BYTES]))).sort()).toEqual(["image", "setup_code"]);
  });
});

describe("choosing a logo on the company screen", () => {
  test("the file is sent with the setup code, said to be kept, and never becomes an answer", async () => {
    // What breaks if this is deleted: the upload half of M42.5.5. The file must reach the server
    // behind the setup code, and the page must say so; the appointment must not carry the file.
    const { idp, seen } = standIn(() =>
      json({ media_type: "image/png", bytes_kept: PNG_BYTES.length, path: "/brand/logo" }),
    );
    const { container } = await openAtTheCompany(idp);

    choose(container, png());

    await waitFor(() => expect(container.textContent).toContain(LOGO_KEPT));
    const [sent] = seen.filter((one) => one.path === LOGO_UPLOAD_PATH);
    expect(sent?.body).toEqual({
      setup_code: CODE,
      image: btoa(String.fromCharCode(...PNG_BYTES)),
    });
  });

  test("a refusal is the server's sentence under its own heading", async () => {
    // What breaks if this is deleted: a rejected file that looks accepted, or a refusal that says
    // nothing a person can act on.
    const { idp } = standIn(() =>
      json({ problem: "PROBLEM-SENTINEL An SVG cannot be used here." }, 422),
    );
    const { container } = await openAtTheCompany(idp);

    choose(container, new File(["<svg/>"], "mark.svg", { type: "image/svg+xml" }));

    await waitFor(() => expect(container.textContent).toContain("PROBLEM-SENTINEL"));
    expect(container.textContent).toContain(LOGO_NOT_KEPT_TITLE);
    expect(container.textContent).not.toContain(LOGO_KEPT);
  });

  test("a 404 is the wizard's one refusal sentence and says nothing of why", async () => {
    // What breaks if this is deleted: `A_SETUP_REFUSAL_NAMES_NO_REASON`. A wrong code, a finished
    // install and an install with no code would read differently here.
    const { idp } = standIn(() => json({ message: "REASON-SENTINEL", problems: [] }, 404));
    const { container } = await openAtTheCompany(idp);

    choose(container, png());

    await waitFor(() => expect(container.textContent).toContain(SETUP_REFUSED_MESSAGE));
    expect(container.textContent).not.toContain("REASON-SENTINEL");
  });

  test("a file over the limit is refused in the page and never sent", async () => {
    // What breaks if this is deleted: a 300 KiB photograph is read into memory, base64-encoded and
    // posted just to be refused by the server.
    const { idp, seen } = standIn(() => json({}));
    const { container } = await openAtTheCompany(idp);

    choose(container, new File([new Uint8Array(MAX_LOGO_BYTES + 1)], "big.png", { type: "image/png" }));

    await waitFor(() => expect(container.textContent).toContain(TOO_LARGE));
    expect(seen.filter((one) => one.path === LOGO_UPLOAD_PATH)).toEqual([]);
  });
});
