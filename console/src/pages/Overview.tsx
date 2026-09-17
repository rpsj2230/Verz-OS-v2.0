/**
 * The first page after sign-in: who the API thinks is asking, and nothing else.
 *
 * **Every fact on this page came from `GET /api/v1/me`, and none of it was read out of a
 * token.** That is the whole reason the page exists in this shape. The console holds an
 * opaque string it never decodes, so the only way it can know who is signed in is to ask,
 * and the answer is computed from grants this browser never receives. `CallerView` is
 * deliberately the caller's own facts with no list of capabilities on it, for the reason its
 * own docstring gives: a capability list would be the first thing cached in a browser and
 * used to decide what to render, which is a permission model in the copy an attacker edits.
 *
 * **The page adds no interpretation to any value.** `assurance` is on the response because
 * it is the one fact a person can act on, and this page still renders it as the word the API
 * sent rather than as a sentence about signing in again. A sentence would be a mapping from
 * a value to a meaning, written here, out of step with the API within a release; the API
 * owns the vocabulary, in the same way `ui/Status.tsx` renders a state word exactly as it
 * arrived. The four values that read as tags render through `Chip`, which has one appearance
 * and no tone, so nothing on this screen can decide that somebody's assurance is alarming.
 *
 * **A field the API did not send contributes nothing.** `primary_department` is nullable and
 * a caller can legitimately have none, so the row is absent rather than present and empty.
 * There is no lock on this page and there must not be one: a lock says the API told us a
 * field exists and withheld it, `/me` sends no `locked`, and inventing one from a null would
 * be the console asserting a refusal nobody made.
 *
 * **A failure is the API's sentence and the trace id, and nothing else.** Including a 404,
 * which on this route means the token authenticated and the subject maps to no principal
 * this company wrote down. Saying so would be the console explaining a refusal it did not
 * observe. See `A_404_IS_NOT_AN_EXPLANATION`.
 *
 * The lock sample that used to be on this page is gone. It was there so the lock could be
 * seen in both themes before any record rendered, and its own comment said to delete it when
 * a real record rendered anywhere. `/records/{entity}` renders one now.
 *
 * **The install card is `/health/ready`, drawn part by part as the API names them.** Database,
 * cache, vault and sign-in are always in the list, each `ready`, `not_ready` or `not_configured`,
 * and `gates` says whether it decides the status; see `brain.readiness`. A 503 carries the same
 * document as a 200, so a degraded install still shows which part is down rather than a failure
 * notice with nothing in it. The words are the API's: nothing here turns a state into a colour.
 *
 * Task ids: M32.5.1.1, M32.5.1.2, M31.4.1, M31.1.1.5
 */

import { useEffect, useState } from "react";
import { request, type ApiResult } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import type { components } from "../api/schema";
import { Chip } from "../ui/Chip";
import { FailureNotice, THAT_DID_NOT_WORK } from "../ui/FailureNotice";

type CallerView = components["schemas"]["CallerView"];
type Health = components["schemas"]["Health"];

/** Where the API says whether each part it depends on is ready. At the root, not under `/api/v1`. */
export const READY_PATH = "/health/ready";

/** The readiness document from a 200, or from a 503, which carries the same one; else null. */
export function healthFrom(result: ApiResult<Health>): Health | null {
  const body: unknown = result.ok ? result.data : result.body;
  if (body === null || typeof body !== "object") {
    return null;
  }
  const candidate = body as Partial<Health>;
  return typeof candidate.status === "string" && Array.isArray(candidate.parts)
    ? (candidate as Health)
    : null;
}

interface Readiness {
  readonly health: Health | null;
  readonly failure: ApiFailure | null;
}

/** One ask of `/health/ready` per mount. Not `useResource`: that drops a 503's body. */
function useReadiness(): Readiness | null {
  const [answer, setAnswer] = useState<Readiness | null>(null);
  useEffect(() => {
    let live = true;
    const controller = new AbortController();
    void (async () => {
      const result = await request<Health>(READY_PATH, { atRoot: true, signal: controller.signal });
      if (live) {
        const health = healthFrom(result);
        setAnswer({ health, failure: health === null && !result.ok ? result.failure : null });
      }
    })();
    return () => {
      live = false;
      controller.abort();
    };
  }, []);
  return answer;
}

/** The install's parts, each as the API named it, with the state word and whether it gates. */
function InstallReadiness() {
  const readiness = useReadiness();
  if (readiness === null) {
    return null;
  }
  return (
    <section className="card" aria-label="This install">
      <h2>This install</h2>
      {readiness.failure ? <FailureNotice failure={readiness.failure} /> : null}
      {readiness.health ? (
        <dl className="fields readiness">
          <div className="fields__row readiness__row" key="status">
            <dt>Status</dt>
            <dd>
              <Chip label={readiness.health.status} />
            </dd>
          </div>
          {readiness.health.parts?.map((part) => (
            <div className="fields__row readiness__row" key={part.name} data-part={part.name}>
              <dt>{part.name}</dt>
              <dd>
                <Chip label={part.state} />
                <Chip label={part.gates ? "decides readiness" : "reported only"} />
              </dd>
            </div>
          ))}
          <div className="fields__row readiness__row" key="commit">
            <dt>Commit</dt>
            <dd>
              <code>{readiness.health.commit}</code>
            </dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}

/** Where the API says who is asking. One route, named once. */
export const ME_PATH = "/me";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = THAT_DID_NOT_WORK;

/**
 * How each fact on the response is shown.
 *
 * A list rather than seven blocks of markup, so that "every fact the API sends about the
 * caller reaches the screen" is a property a test can hold against the Python model rather
 * than a thing somebody checks by eye. `tests/overview-page.test.tsx` reads the field names
 * off `brain.api_routes.CallerView` and fails when this list and that model disagree, in
 * either direction: a field added there and not here would arrive and be dropped silently,
 * which is the failure nobody notices.
 *
 * `chip` says the value is a short closed-vocabulary word rather than prose. It chooses
 * between two appearances that carry no colour and no severity, so it is a layout decision
 * and not a tone. `code` is for the two identifiers that exist to be copied into a message
 * to somebody.
 */
export const CALLER_FIELDS: readonly {
  readonly name: keyof CallerView;
  readonly label: string;
  readonly as: "text" | "chip" | "code";
}[] = [
  { name: "display_name", label: "Name", as: "text" },
  { name: "principal_id", label: "Principal", as: "code" },
  { name: "primary_department", label: "Department", as: "chip" },
  { name: "employment", label: "Employment", as: "chip" },
  { name: "assurance", label: "Assurance", as: "chip" },
  { name: "channel", label: "Channel", as: "chip" },
  { name: "ent_hash", label: "Entitlement digest", as: "code" },
  // Both rendered as the API spelled them: each verb its own chip, the flag as the word `true` or
  // `false`. What they mean for a person is the shell's banner's to say, not this page's.
  { name: "withheld_verbs", label: "Verbs withheld at this sign-in", as: "chip" },
  { name: "second_factor_needed", label: "Second factor needed", as: "chip" },
];

/** The words one field arrived as: a string, each entry of a list, or a flag spelled out. */
export function spelled(value: unknown): readonly string[] {
  if (typeof value === "string") {
    return value === "" ? [] : [value];
  }
  if (typeof value === "boolean") {
    return [String(value)];
  }
  if (Array.isArray(value)) {
    return value.filter((one): one is string => typeof one === "string" && one !== "");
  }
  return [];
}

/** One value, in the appearance its row asked for. Never a value this file composed. */
function CallerValue({ value, as }: { readonly value: string; readonly as: "text" | "chip" | "code" }) {
  if (as === "chip") {
    return <Chip label={value} />;
  }
  if (as === "code") {
    return <code>{value}</code>;
  }
  return <>{value}</>;
}

export function Overview() {
  const caller = useResource<CallerView>(ME_PATH);

  return (
    <article className="page">
      <h1>Overview</h1>
      <p className="lede">
        Who this console is signed in as, and whether this install is ready, according to the API.
      </p>

      <section className="card">
        <h2>You</h2>

        {caller.failure ? (
          <FailureNotice failure={caller.failure} />
        ) : null}

        {caller.busy ? (
          <p className="note" role="status">
            Loading.
          </p>
        ) : null}

        {caller.data ? (
          <dl className="fields">
            {CALLER_FIELDS.map((field) => {
              const values = spelled(caller.data?.[field.name]);
              // Absent stays absent, and so does an empty list. A row rendered with nothing in
              // it is a shape where a fact would be, and two people comparing screens can read a
              // shape.
              if (values.length === 0) {
                return null;
              }
              return (
                <div className="fields__row" key={field.name}>
                  <dt>{field.label}</dt>
                  <dd>
                    {values.map((value) => (
                      <CallerValue key={value} value={value} as={field.as} />
                    ))}
                  </dd>
                </div>
              );
            })}
          </dl>
        ) : null}
      </section>

      <InstallReadiness />
    </article>
  );
}
