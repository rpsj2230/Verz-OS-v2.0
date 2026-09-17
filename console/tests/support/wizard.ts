/**
 * The setup wizard and its catalogue, read out of the Python source.
 *
 * `src/setup/wizard.ts` copies the screens of `brain.setup_wizard.WIZARD` and the English of
 * `brain.locale.MESSAGES`, because no route serves either. A copy compared with itself is
 * green for every value it could hold, so these readers go to the original, in the narrow and
 * throwing style of `support/python.ts`: a shape that has moved throws, and never returns an
 * empty list that every comparison would then agree with.
 */

import { backendEnumMembers } from "./python";
import { extractOne, readRepoFile } from "./repo";

const WIZARD_MODULE = "src/brain/setup_wizard.py";
const LOCALE_MODULE = "src/brain/locale.py";
const PROVIDER_KEYS = "src/brain/ops/provider_keys.py";

export interface BackendQuestion {
  readonly name: string;
  readonly required: boolean;
  readonly secret: boolean;
  readonly maxChars: number;
  readonly choices: readonly string[] | null;
}

export interface BackendStep {
  readonly key: string;
  readonly titleKey: string;
  readonly skippable: boolean;
  readonly questions: readonly BackendQuestion[];
}

/** One block from a line matching `opens` to the first line that is `)` alone. */
function blockFrom(source: string, opens: RegExp, what: string): string {
  const found = opens.exec(source);
  if (!found) {
    throw new Error(`Could not find ${what}; the source has moved and nothing is being checked.`);
  }
  const after = source.slice(found.index + found[0].length);
  const closes = /^\)$/m.exec(after);
  if (!closes) {
    throw new Error(`${what} never closes; the parser is stale.`);
  }
  return after.slice(0, closes.index);
}

function quoted(text: string): string[] {
  return [...text.matchAll(/"([^"]*)"/g)].map((one) => one[1] ?? "");
}

function integerConstant(source: string, name: string): number {
  return Number(extractOne(source, new RegExp(`^${name}: Final = (\\d+)$`, "m"), name));
}

/** The closed list one `check=` expression allows, or a throw for one nobody taught this. */
function choicesFor(expression: string, wizard: string): string[] {
  if (expression === "_one_of(tuple(STAFF_SOURCE_BROKERS))") {
    const block = blockFrom(wizard, /^STAFF_SOURCE_BROKERS: .*$/m, "STAFF_SOURCE_BROKERS");
    return [...block.matchAll(/^\s+"(\w+)": "/gm)].map((one) => one[1] ?? "");
  }
  if (expression === "_one_of(STEWARD_IS_ADMINISTRATOR_ANSWERS)") {
    return quoted(
      extractOne(
        wizard,
        /^STEWARD_IS_ADMINISTRATOR_ANSWERS: [^=]+= \(([^)]*)\)$/m,
        "STEWARD_IS_ADMINISTRATOR_ANSWERS",
      ),
    );
  }
  if (expression === "_one_of(MODEL_PROFILES)") {
    return quoted(extractOne(wizard, /^MODEL_PROFILES: [^=]+= \(([^)]*)\)$/m, "MODEL_PROFILES"));
  }
  if (expression === "_one_of(tuple(one.slug for one in PROVIDER_SLOTS))") {
    const block = blockFrom(readRepoFile(PROVIDER_KEYS), /^PROVIDER_SLOTS: .*$/m, "PROVIDER_SLOTS");
    return [...block.matchAll(/slug="(\w+)"/g)].map((one) => one[1] ?? "");
  }
  throw new Error(`No reader for ${expression}. A question gained a closed list; teach this file.`);
}

/** Every step of `WIZARD`, in order, with its questions as the console needs them. */
export function backendWizard(): BackendStep[] {
  const wizard = readRepoFile(WIZARD_MODULE);
  const stepIds = backendEnumMembers(WIZARD_MODULE, "StepId");
  const maxima: Record<string, number> = {
    MAX_ANSWER_CHARS: integerConstant(wizard, "MAX_ANSWER_CHARS"),
    MAX_KEY_CHARS: integerConstant(wizard, "MAX_KEY_CHARS"),
  };
  const block = blockFrom(wizard, /^WIZARD: Final\[tuple\[Step, \.\.\.\]\] = \($/m, "WIZARD");
  const starts = [...block.matchAll(/^ {4}Step\(/gm)].map((one) => one.index ?? 0);
  if (starts.length === 0) {
    throw new Error("Parsed no steps from WIZARD; the parser is stale.");
  }
  return starts.map((start, index) => {
    const chunk = block.slice(start, starts[index + 1] ?? block.length);
    const member = extractOne(chunk, /key=StepId\.(\w+)/, "a step's key");
    const key = stepIds[member];
    if (key === undefined) {
      throw new Error(`StepId.${member} is not a member of StepId.`);
    }
    const calls = [...chunk.matchAll(/_q\(\s*"(\w+)"/g)];
    const questions = calls.map((call, at) => {
      const segment = chunk.slice(call.index ?? 0, calls[at + 1]?.index ?? chunk.length);
      const check = /check=(_one_of\((?:[^()]|\([^()]*\))*\))/.exec(segment)?.[1];
      const ceiling = /\bmax_chars=(\w+)\b/.exec(segment)?.[1] ?? "MAX_ANSWER_CHARS";
      const maxChars = maxima[ceiling];
      if (maxChars === undefined) {
        throw new Error(`${call[1] ?? ""} is capped by ${ceiling}, which this reader does not know.`);
      }
      return {
        name: call[1] ?? "",
        required: !/\brequired=False\b/.test(segment),
        secret: /\bsecret=True\b/.test(segment),
        maxChars,
        choices: check === undefined ? null : choicesFor(check, wizard),
      };
    });
    return {
      key,
      titleKey: extractOne(chunk, /title_key="([^"]+)"/, `the title key of ${key}`),
      skippable: /\bskippable=True\b/.test(chunk),
      questions,
    };
  });
}

/** The English sentence `brain.locale.MESSAGES` holds under one key. */
export function catalogueEnglish(key: string): string {
  const source = readRepoFile(LOCALE_MODULE);
  const escaped = key.replace(/\./g, "\\.");
  return extractOne(source, new RegExp(`"${escaped}": \\{\\s*"en": "([^"]*)"`), `the English for ${key}`);
}

/** Every catalogue key under one prefix, such as `setup.error.`. Throws when there are none. */
export function catalogueKeys(prefix: string): string[] {
  const source = readRepoFile(LOCALE_MODULE);
  const escaped = prefix.replace(/\./g, "\\.");
  const keys = [...source.matchAll(new RegExp(`^ {4}"(${escaped}[\\w.]+)": \\{`, "gm"))].map(
    (one) => one[1] ?? "",
  );
  if (keys.length === 0) {
    throw new Error(`No catalogue keys under ${prefix}; the parser is stale.`);
  }
  return keys;
}
