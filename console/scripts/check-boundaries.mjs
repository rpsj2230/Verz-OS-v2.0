/**
 * The rules in this console that are worth more than a paragraph, checked mechanically.
 *
 * **First run on 2026-09-08, on Node 24, clean.** It had never been executed before that:
 * there was no Node toolchain on the machine it was written on, so it had been reasoned
 * about and not run, and this paragraph said so. Every rule below the first seven was added
 * afterwards and has been run. It has no dependencies, so `node scripts/check-boundaries.mjs`
 * is the whole of what it needs, and CI runs it on every push.
 *
 * **Why a grep and not a linter rule.** ESLint would express most of this better and would
 * be another toolchain to pin, configure and keep working. Every rule here is a rule about
 * a literal appearing in a file, which is the one thing a grep is genuinely good at, and
 * the cost of being blunt is a false positive that a written reason can wave through.
 *
 * Each rule says what breaks if it is deleted. That is not decoration either: a rule
 * nobody can justify is a rule the next person removes to make a build pass, and they will
 * be right to.
 *
 * A line may opt out by carrying the marker `boundary-ok:` followed by a reason. The
 * requirement to write the reason is the point, in the same spirit as the repository's
 * rule about explaining a `cast`.
 */

import { readFile, readdir } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const CONSOLE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(CONSOLE_ROOT, "src");
const INDEX_HTML = join(CONSOLE_ROOT, "index.html");
const THEME_MODULE = join(SRC, "theme", "theme.ts");

const OPT_OUT = "boundary-ok:";

/**
 * Each rule: a name, a pattern, the files allowed to match it, and the sentence that
 * explains why anybody should care. Paths are relative to the console directory and use
 * forward slashes.
 */
const RULES = [
  {
    name: "no token parsing",
    pattern: /\batob\(|jwt-decode|jwtDecode|parseJwt|decodeJwt/,
    allow: [],
    why:
      "The console must never read a token's contents. It holds an opaque string, sends " +
      "it, and does what the API answers. Decoding one is how a browser acquires a second " +
      "permission model: the first role check written against a claim is a rule the API " +
      "never agreed to, and the copy in the browser is the copy an attacker edits.",
  },
  {
    name: "no authorisation decisions in the client",
    pattern: /\b(hasRole|hasPermission|hasCapability|requireRole|isAdmin|canRead)\b/,
    allow: [],
    why:
      "Every permission decision belongs to the API, computed per request from grants " +
      "this browser never receives. A function with one of these names in this codebase " +
      "is a second permission model, and two models disagree eventually and silently.",
  },
  {
    name: "tokens are never stored",
    pattern: /\blocalStorage\b/,
    allow: ["src/theme/theme.ts"],
    why:
      "Access and refresh tokens live in memory and die with the page. The realm gives an " +
      "SSO session ten hours, so a refresh token in the local store would be a ten-hour " +
      "credential readable by any script on this origin. The theme preference is allowed " +
      "there because it is a property of the screen, not of the person.",
  },
  {
    name: "session storage is for the sign-in handshake only",
    pattern: /\bsessionStorage\b/,
    allow: ["src/auth/pkce.ts"],
    why:
      "The PKCE verifier and the state value have to survive a full page navigation, so " +
      "they cannot be held in a variable. Nothing else in this console has that problem, " +
      "and a second writer is how a token ends up in storage by accident.",
  },
  {
    name: "one place talks to the network",
    pattern: /\bfetch\(/,
    allow: ["src/api/client.ts", "src/auth/discovery.ts", "src/auth/session.ts"],
    why:
      "The token is attached in one place and failures are shaped in one place, so a " +
      "reviewer asking what this console can reach reads one file. The second call site " +
      "is always the one that forgets the failure handling.",
  },
  {
    name: "no implicit flow and no password grant",
    pattern: /response_type=token|id_token token|grant_type=password|type="password"/,
    allow: [],
    why:
      "The realm has implicitFlowEnabled false and directAccessGrantsEnabled false on " +
      "every client. The implicit flow puts a token in a URL fragment, which lands in " +
      "browser history and referrer headers; the password grant skips the browser flow " +
      "and therefore the second factor the realm makes mandatory. A password field here " +
      "would collect a credential this page cannot verify it is entitled to see.",
  },
  {
    name: "no raw HTML from a payload",
    pattern: /dangerouslySetInnerHTML/,
    allow: [],
    why:
      "Everything this console renders came from a system of record through the gate. " +
      "Rendering any of it as HTML is script injection with the company's own data as the " +
      "vector, and it also breaks the lock: markup in a field would render as markup.",
  },
  {
    name: "no positive tab order",
    pattern: /tabIndex=\{?\s*["']?[1-9]/,
    allow: [],
    why:
      "A positive tabindex lifts one element out of the document's own order and puts it " +
      "ahead of everything with a zero, which is every other control on the page. One of " +
      "them reorders the whole console for anybody navigating by keyboard, and the order " +
      "it produces is not the one somebody reading the markup would predict. Nothing here " +
      "needs one: every control is a native element, so the tab order is the source order.",
  },
  {
    name: "no service worker",
    pattern: /serviceWorker|navigator\.serviceWorker|workbox|registerSW/,
    allow: [],
    why:
      "The console is installable and caches nothing, and those two go together. A service " +
      "worker's whole purpose is to serve something without asking the network, which for " +
      "this application means a copy of a client's data on somebody's phone: readable after " +
      "they leave the company, after their grants are revoked, and after the row it came " +
      "from was deleted. It is the disclosure the entire permission model exists to " +
      "prevent, arriving through a performance feature. index.html says the same thing " +
      "beside the manifest link, because that is where somebody adding one would be.",
  },
];

async function sourceFiles(directory) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = join(directory, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "generated") {
        // Generated from the API's own document. It is not hand-written code and holding
        // it to these rules would mean editing a file that is rewritten on every run.
        continue;
      }
      found.push(...(await sourceFiles(full)));
    } else if (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")) {
      found.push(full);
    }
  }
  return found;
}

function relativePath(full) {
  return relative(CONSOLE_ROOT, full).split("\\").join("/");
}

async function checkRules(failures) {
  for (const file of await sourceFiles(SRC)) {
    const shown = relativePath(file);
    const lines = (await readFile(file, "utf8")).split("\n");
    lines.forEach((line, index) => {
      if (line.includes(OPT_OUT)) {
        return;
      }
      for (const rule of RULES) {
        if (rule.pattern.test(line) && !rule.allow.includes(shown)) {
          failures.push({
            where: `${shown}:${index + 1}`,
            rule: rule.name,
            why: rule.why,
            line: line.trim(),
          });
        }
      }
    });
  }
}

/**
 * The theme storage key is written twice: once in a blocking script in index.html that
 * runs before the first paint, and once in the module that owns the preference. The script
 * cannot import the module and still block paint, so the literal is duplicated and this is
 * the check that keeps the two honest. If they drift, the page loads in the wrong theme
 * and then corrects itself, which is a flash nobody files a bug about.
 */
async function checkThemeKey(failures) {
  const html = await readFile(INDEX_HTML, "utf8");
  const module = await readFile(THEME_MODULE, "utf8");
  const declared = /export const THEME_STORAGE_KEY = "([^"]+)";/.exec(module);
  if (!declared) {
    failures.push({
      where: relativePath(THEME_MODULE),
      rule: "theme key is declared once",
      why: "No THEME_STORAGE_KEY export of the expected shape, so nothing can be compared.",
      line: "",
    });
    return;
  }
  if (!html.includes(`"${declared[1]}"`)) {
    failures.push({
      where: "index.html",
      rule: "theme key matches the pre-paint script",
      why:
        `The module stores the theme under "${declared[1]}" and index.html does not read ` +
        "that key. The stored preference is ignored until React starts, which is the " +
        "flash of the wrong theme the blocking script exists to prevent.",
      line: "",
    });
  }
}

/** Every stylesheet under a directory, at any depth. */
async function stylesheets(directory) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = join(directory, entry.name);
    if (entry.isDirectory()) {
      found.push(...(await stylesheets(full)));
    } else if (entry.name.endsWith(".css")) {
      found.push(full);
    }
  }
  return found;
}

/**
 * The focus ring, which is the only thing telling somebody navigating by keyboard where
 * they are.
 *
 * Two questions, and the second is the one that goes stale quietly. First: does anything
 * remove the outline. `outline: none` is the single most common accessibility regression on
 * the web and it arrives as a tidy-up, because the default ring is ugly and the person
 * removing it is looking at a mouse pointer. Second: is there still a rule that draws one.
 * A stylesheet with no `:focus-visible` rule passes the first check perfectly and leaves the
 * console with whatever the browser does by default, which in a design that has restyled its
 * buttons is frequently nothing.
 *
 * The stylesheets are checked here rather than in `RULES` because `sourceFiles` walks
 * TypeScript only. Every `.css` under `src`, not only the ones in `src/styles`: the focus
 * colour itself lives in `src/theme/tokens.css`, and a scan of one directory would have
 * been a scan that could not see the file most likely to be tidied.
 */
async function checkFocusStates(failures) {
  const sheets = await stylesheets(SRC);
  let drawsAFocusRing = false;
  for (const sheet of sheets) {
    const text = await readFile(sheet, "utf8");
    if (/:focus-visible[^{]*\{[^}]*outline\s*:/.test(text)) {
      drawsAFocusRing = true;
    }
    text.split("\n").forEach((line, index) => {
      if (line.includes(OPT_OUT)) {
        return;
      }
      if (/outline\s*:\s*(none|0)\s*(;|$|!)/.test(line)) {
        failures.push({
          where: `${relativePath(sheet)}:${index + 1}`,
          rule: "the focus outline is never removed",
          why:
            "Removing the outline leaves somebody navigating by keyboard with no way to " +
            "tell where they are on the page, and the person removing it is looking at a " +
            "mouse pointer and cannot see the loss. If a control genuinely needs a " +
            "different ring, draw the different ring rather than taking the default away.",
          line: line.trim(),
        });
      }
    });
  }
  if (!drawsAFocusRing) {
    failures.push({
      where: "src",
      rule: "something draws a focus ring",
      why:
        "No stylesheet has a `:focus-visible` rule that sets an outline. Nothing is " +
        "removing one either, which is why the rule above passes, and the console is left " +
        "with whatever the browser draws by default on controls this design has restyled.",
      line: "",
    });
  }
}

/** Elements that are not focusable and not announced as controls. */
const NOT_A_CONTROL = new Set([
  "div",
  "span",
  "li",
  "td",
  "tr",
  "p",
  "section",
  "article",
  "header",
  "footer",
  "nav",
  "ul",
  "ol",
  "main",
  "img",
  "svg",
]);

/**
 * A click handler on something the keyboard cannot reach.
 *
 * A `div` with an `onClick` works perfectly for a mouse and does not exist for anybody
 * else: it takes no focus, it is announced as nothing, and Enter does not activate it. The
 * fix is almost always a `button`, which is why this refuses rather than asking for the
 * three attributes that would make the `div` behave like one.
 *
 * Found by scanning backwards from each `onClick` to the tag that opens it, rather than by
 * matching an opening tag forwards. A JSX attribute list contains `=>`, so a pattern for
 * `<div ...>` stops at the first arrow function and reports the wrong element or none.
 * Blunt, in the same spirit as the rest of this file, and a genuine exception can carry the
 * opt-out marker with a reason.
 */
async function checkClickablesAreFocusable(failures) {
  for (const file of await sourceFiles(SRC)) {
    if (!file.endsWith(".tsx")) {
      continue;
    }
    const text = await readFile(file, "utf8");
    for (const match of text.matchAll(/onClick\s*=/g)) {
      const opens = text.lastIndexOf("<", match.index);
      if (opens < 0) {
        continue;
      }
      const named = /^<([A-Za-z][A-Za-z0-9]*)/.exec(text.slice(opens, opens + 40));
      if (!named || !NOT_A_CONTROL.has(named[1])) {
        continue;
      }
      const attributes = text.slice(opens, match.index + 400);
      if (/\brole=|\bonKeyDown=|\bonKeyUp=/.test(attributes)) {
        continue;
      }
      const before = text.slice(0, match.index);
      const lineNumber = before.split("\n").length;
      const line = text.split("\n")[lineNumber - 1] ?? "";
      if (line.includes(OPT_OUT)) {
        continue;
      }
      failures.push({
        where: `${relativePath(file)}:${lineNumber}`,
        rule: "a click handler belongs on something the keyboard can reach",
        why:
          `<${named[1]}> takes no focus, is announced as nothing, and does not activate on ` +
          "Enter, so a click handler on one works for a mouse and does not exist for " +
          "anybody else. Use a button. If this really is not a control, the handler is on " +
          "the wrong element.",
        line: line.trim(),
      });
    }
  }
}


const failures = [];
await checkRules(failures);
await checkThemeKey(failures);
await checkFocusStates(failures);
await checkClickablesAreFocusable(failures);

if (failures.length === 0) {
  console.log("check-boundaries: clean");
  process.exit(0);
}

for (const failure of failures) {
  console.error(`\n${failure.where}  [${failure.rule}]`);
  if (failure.line) {
    console.error(`  ${failure.line}`);
  }
  console.error(`  ${failure.why}`);
}
console.error(
  `\ncheck-boundaries: ${failures.length} problem(s). If one of them is genuinely ` +
    `correct, end the line with "${OPT_OUT} <reason>" and say why.`,
);
process.exit(1);
