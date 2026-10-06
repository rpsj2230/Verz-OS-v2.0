/**
 * The two people the harness signs in as, and the values the job minted for them this run.
 *
 * Names and ids are `e2e/fixtures/people.json`, read rather than restated, so the realm and the
 * browser cannot disagree about who is who. Credentials come from the job's environment and from
 * nowhere else: `brain.ops.browser_harness.A_CREDENTIAL_IN_A_FIXTURE_IS_A_CREDENTIAL_IN_A_REPOSITORY`.
 *
 * Task ids: M27.10.6
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

interface FixturePerson {
  readonly id: string;
  readonly username: string;
  readonly email: string;
  readonly firstName: string;
  readonly lastName: string;
}

const FIXTURE = fileURLToPath(new URL("../fixtures/people.json", import.meta.url));
const PEOPLE: readonly FixturePerson[] = JSON.parse(readFileSync(FIXTURE, "utf8")) as FixturePerson[];

function minted(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is not set: the job mints it before the stack starts`);
  }
  return value;
}

function person(username: string): FixturePerson {
  const found = PEOPLE.find((one) => one.username === username);
  if (!found) {
    throw new Error(`${username} is not in e2e/fixtures/people.json`);
  }
  return found;
}

export interface Person {
  readonly subject: string;
  readonly username: string;
  readonly email: string;
  readonly fullName: string;
  readonly password: () => string;
}

function described(username: string, passwordVariable: string): Person {
  const one = person(username);
  return {
    subject: one.id,
    username: one.username,
    email: one.email,
    fullName: `${one.firstName} ${one.lastName}`,
    password: () => minted(passwordVariable),
  };
}

/** The first administrator: a password and a one-time code. */
export const ADMIN = { ...described("e2e-admin", "E2E_ADMIN_PASSWORD"), codeSecret: () => minted("E2E_ADMIN_CODE_SECRET") };

/** The data steward the wizard names: a password alone. */
export const READER = described("e2e-reader", "E2E_READER_PASSWORD");

/** The setup code the job minted beside the install's own instant, as the installer does. */
export const setupCode = (): string => minted("BRAIN_SETUP_SECRET");
