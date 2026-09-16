/**
 * Webhooks: who outside the company is told when something happens here, where each is told,
 * whether its signing secret is held, what happened to its deliveries, and the three controls.
 *
 * `docs/screens.html` does not draw this screen, so it takes the design's general shape and says
 * in words what the platform does and cannot do yet: how delivery works and what the dispatch last
 * did, which channel's check for an arriving webhook is written, and that an automation's inbound
 * credential is listed nowhere. Each of those sentences is the API's, so the day one changes the
 * screen changes with it.
 *
 * **Every write is confirmed, and the confirmation says what happens in the API's words.**
 * Registering, replacing a secret and switching off each open `ConfirmAction` with the sentence the
 * route served. A success says what changed and when; a refusal is the API's problems beside their
 * fields, or its message.
 *
 * **A secret is typed into a plain text field and forgotten the moment it is sent.** A password
 * field is refused by `scripts/check-boundaries.mjs`, for the reason written there, so the field is
 * `autoComplete="off"` and `spellCheck={false}` as the setup wizard's is, and the value is cleared
 * from the page's state as soon as the request leaves, whatever comes back.
 *
 * **Nothing here decides who may change a subscriber.** `manageable` only decides whether a control
 * is drawn, and the route decides again.
 *
 * Task ids: M27.8.12, M27.8.5
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import {
  CHANGE_LABELS,
  REGISTER_API_PATH,
  STATE_FILTERS,
  STATE_FILTER_LABELS,
  VERIFICATION_LABELS,
  WEBHOOKS_API_PATH,
  narrowed,
  blankRegistrationProblems,
  blankSecretProblems,
  dispatcherOutcome,
  problemsFor,
  readProblems,
  readWebhooks,
  registrationBody,
  secretApiPath,
  secretBody,
  secretSentence,
  stateSentence,
  switchOffApiPath,
  when,
  type DispatcherBody,
  type Problem,
  type StateFilter,
  type SubscriberRow,
  type WebhooksBody,
} from "./webhooksQuery";

export const WEBHOOKS_HEADING = "Webhooks";
export const WEBHOOKS_CRUMB = "Operate › Webhooks";
export const WEBHOOKS_LEDE =
  "Who outside the company is told when something happens here, where they are told, and " +
  "whether the secret that signs what they are sent is held. A subscriber is told identifiers, " +
  "never content.";

export const READING_WEBHOOKS = "Reading the webhook subscribers.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NO_SUBSCRIBERS = "No subscriber is registered.";
export const NONE_MATCH = "No subscriber on this page matches.";
export const NOT_MANAGEABLE =
  "Registering and changing webhook subscribers needs the webhook management grant over the " +
  "whole company, which you do not hold, so no subscriber is listed here.";

export const REGISTER_LABEL = "Register";
export const REGISTER_CONFIRM = "Register subscriber";
export const REPLACE_LABEL = "Replace secret";
export const SWITCH_OFF_LABEL = "Switch off";
export const KEEP_LABEL = "Change nothing";

function Failure({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
}

function FieldProblems({ problems, field }: { readonly problems: readonly Problem[]; readonly field: string }) {
  const found = problemsFor(problems, field);
  if (found.length === 0) {
    return null;
  }
  return (
    <ul className="field-description" aria-label={`Problems with ${field}`}>
      {found.map((one) => (
        <li key={one}>{one}</li>
      ))}
    </ul>
  );
}

type Pending =
  | { readonly kind: "register"; readonly id: string; readonly endpoint: string; readonly kinds: readonly string[]; readonly secret: string }
  | { readonly kind: "replace"; readonly id: string; readonly secret: string }
  | { readonly kind: "switch_off"; readonly id: string };

function readTold(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const told = (payload as { told?: unknown }).told;
  return typeof told === "string" ? told : "";
}

function Dispatcher({ dispatcher }: { readonly dispatcher: DispatcherBody }) {
  return (
    <div>
      <p className="note">{dispatcher.told}</p>
      {dispatcher.last_started_at === null ? null : (
        <dl className="fields" aria-label="The last run">
          <dt>Last run started</dt>
          <dd>{when(dispatcher.last_started_at)}</dd>
          <dt>How it ended</dt>
          <dd>{dispatcherOutcome(dispatcher)}</dd>
          {dispatcher.last_report === null ? null : (
            <>
              <dt>What it did</dt>
              <dd>{dispatcher.last_report}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}

function SubscriberDetail({ row }: { readonly row: SubscriberRow }) {
  if (row.deliveries.length === 0 && row.changes.length === 0) {
    return null;
  }
  return (
    <section className="card" aria-label={`What happened to ${row.subscriber_id}`}>
      <h3>
        <code>{row.subscriber_id}</code>
      </h3>
      {row.deliveries.length === 0 ? null : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={`Recent deliveries to ${row.subscriber_id}`}>
            <thead>
              <tr>
                <th scope="col">Kind</th>
                <th scope="col">Where it got to</th>
                <th scope="col">Attempts</th>
                <th scope="col">Last attempt</th>
                <th scope="col">Next try</th>
                <th scope="col">Why</th>
              </tr>
            </thead>
            <tbody>
              {row.deliveries.map((one, index) => (
                <tr key={`${one.occurred_at}-${String(index)}`}>
                  <td>{one.kind}</td>
                  <td>{one.state}</td>
                  <td>{one.attempts}</td>
                  <td>{when(one.last_attempt_at)}</td>
                  <td>{when(one.next_attempt_at)}</td>
                  <td>{one.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {row.changes.length === 0 ? null : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={`Changes to ${row.subscriber_id}`}>
            <thead>
              <tr>
                <th scope="col">Change</th>
                <th scope="col">By</th>
                <th scope="col">When</th>
              </tr>
            </thead>
            <tbody>
              {row.changes.map((one, index) => (
                <tr key={`${one.changed_at}-${String(index)}`}>
                  <td>{CHANGE_LABELS[one.change] ?? one.change}</td>
                  <td>
                    <code>{one.changed_by}</code>
                  </td>
                  <td>{when(one.changed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function WebhookPage({
  page,
  onChanged,
}: {
  readonly page: WebhooksBody;
  readonly onChanged: (sentence: string) => void;
}) {
  const [state, setState] = useState<StateFilter>("all");
  const [search, setSearch] = useState("");
  const [id, setId] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [kinds, setKinds] = useState<string[]>([]);
  const [secret, setSecret] = useState("");
  const [rotating, setRotating] = useState<string | null>(null);
  const [rotation, setRotation] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const send = useCallback(
    (asked: Pending) => {
      setBusy(true);
      // The secret leaves the page's state before the request does. See the module note.
      setSecret("");
      setRotation("");
      void (async () => {
        const result =
          asked.kind === "register"
            ? await request<unknown>(REGISTER_API_PATH, {
                method: "POST",
                body: registrationBody(asked.id, asked.endpoint, asked.kinds, asked.secret),
              })
            : asked.kind === "replace"
              ? await request<unknown>(secretApiPath(asked.id), {
                  method: "POST",
                  body: secretBody(asked.secret),
                })
              : await request<unknown>(switchOffApiPath(asked.id), { method: "POST" });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          const found = result.failure.status === 422 ? readProblems(result.body) : null;
          setProblems(found ?? []);
          setFailure(found === null ? result.failure : null);
          return;
        }
        setProblems([]);
        setFailure(null);
        setRotating(null);
        onChanged(readTold(result.data));
      })();
    },
    [onChanged],
  );

  const shown = narrowed(page.subscribers, state, search);

  function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure(null);
    // Blank fields are said beside their fields before anything is confirmed or sent.
    const blank = blankRegistrationProblems(id, endpoint, kinds, secret);
    setProblems(blank);
    if (blank.length > 0) {
      return;
    }
    setPending({ kind: "register", id, endpoint, kinds, secret });
  }

  const confirmation =
    pending === null ? null : pending.kind === "register" ? (
      <ConfirmAction
        question={`Register ${pending.id || "this subscriber"} to be told at ${pending.endpoint || "this address"}?`}
        consequence={page.registering}
        confirmLabel={REGISTER_CONFIRM}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={() => {
          send(pending);
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    ) : pending.kind === "replace" ? (
      <ConfirmAction
        question={`Replace the signing secret of ${pending.id}?`}
        consequence={page.replacing}
        confirmLabel={REPLACE_LABEL}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={() => {
          send(pending);
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    ) : (
      <ConfirmAction
        question={`Switch off ${pending.id}?`}
        consequence={page.switching_off}
        confirmLabel={SWITCH_OFF_LABEL}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={() => {
          send(pending);
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    );

  return (
    <>
      {failure === null ? null : <Failure failure={failure} />}
      {confirmation}

      <section className="card">
        <h2>Subscribers</h2>
        <p className="note">{page.delivery}</p>
        {page.dispatcher === null ? null : <Dispatcher dispatcher={page.dispatcher} />}
        {!page.manageable ? (
          <p className="note">{NOT_MANAGEABLE}</p>
        ) : (
          <>
            {page.vault === "ready" ? null : <p className="note">{page.vault_told}</p>}
            {page.subscribers.length === 0 ? (
              <p className="note">{NO_SUBSCRIBERS}</p>
            ) : (
              <>
                <form className="form" aria-label="Narrow the subscribers" onSubmit={(event) => event.preventDefault()}>
                  <label className="control-label">
                    State{" "}
                    <select
                      className="form-control"
                      value={state}
                      onChange={(event) => {
                        setState(event.target.value as StateFilter);
                      }}
                    >
                      {STATE_FILTERS.map((one) => (
                        <option key={one} value={one}>
                          {STATE_FILTER_LABELS[one]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="control-label">
                    Id or address{" "}
                    <input
                      className="form-control"
                      type="search"
                      value={search}
                      onChange={(event) => {
                        setSearch(event.target.value);
                      }}
                    />
                  </label>
                </form>
                {shown.length === 0 ? (
                  <p className="note">{NONE_MATCH}</p>
                ) : (
                  <div className="grid__scroll">
                    <table className="grid__table" aria-label="Webhook subscribers">
                      <thead>
                        <tr>
                          <th scope="col">Subscriber</th>
                          <th scope="col">Told at</th>
                          <th scope="col">Told about</th>
                          <th scope="col">State</th>
                          <th scope="col">Signing secret</th>
                          <th scope="col">Last delivered</th>
                          <th scope="col">Controls</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shown.map((row) => (
                          <tr key={row.subscriber_id}>
                            <td>
                              <code>{row.subscriber_id}</code> registered by <code>{row.created_by}</code>
                            </td>
                            <td>
                              <code>{row.endpoint}</code>
                            </td>
                            <td>{row.kinds.join(", ")}</td>
                            <td>{stateSentence(row)}</td>
                            <td>{secretSentence(row)}</td>
                            <td>{row.last_delivered_at ? when(row.last_delivered_at) : "Never"}</td>
                            <td>
                              {row.active ? (
                                <>
                                  <button
                                    type="button"
                                    className="button"
                                    aria-label={`${REPLACE_LABEL}: ${row.subscriber_id}`}
                                    disabled={busy}
                                    onClick={() => {
                                      setProblems([]);
                                      setRotation("");
                                      setRotating(row.subscriber_id);
                                    }}
                                  >
                                    {REPLACE_LABEL}
                                  </button>{" "}
                                  <button
                                    type="button"
                                    className="button"
                                    aria-label={`${SWITCH_OFF_LABEL}: ${row.subscriber_id}`}
                                    disabled={busy}
                                    onClick={() => {
                                      setFailure(null);
                                      setPending({ kind: "switch_off", id: row.subscriber_id });
                                    }}
                                  >
                                    {SWITCH_OFF_LABEL}
                                  </button>
                                </>
                              ) : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
            {page.findings.length === 0 ? null : (
              <ul aria-label="Findings about the subscriptions">
                {page.findings.map((one) => (
                  <li key={one} className="note">
                    {one}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      {rotating === null ? null : (
        <section className="card">
          <h2>Replace the signing secret of {rotating}</h2>
          <form
            className="form"
            aria-label={`Replace the signing secret of ${rotating}`}
            onSubmit={(event) => {
              event.preventDefault();
              setFailure(null);
              const blank = blankSecretProblems(rotation);
              setProblems(blank);
              if (blank.length > 0) {
                return;
              }
              setPending({ kind: "replace", id: rotating, secret: rotation });
            }}
          >
            <label className="control-label">
              New signing secret{" "}
              <input
                className="form-control"
                type="text"
                autoComplete="off"
                spellCheck={false}
                value={rotation}
                onChange={(event) => {
                  setRotation(event.target.value);
                }}
              />
            </label>
            <FieldProblems problems={problems} field="secret" />
            <p className="field-description">
              At least {page.secret_minimum} characters, generated rather than typed. It is never shown again.
            </p>
            <div className="form-actions">
              <button
                type="button"
                className="button"
                onClick={() => {
                  setRotating(null);
                  setRotation("");
                }}
              >
                {KEEP_LABEL}
              </button>{" "}
              <button type="submit" className="button" disabled={busy}>
                {REPLACE_LABEL}
              </button>
            </div>
          </form>
        </section>
      )}

      {page.subscribers.map((row) => (
        <SubscriberDetail key={row.subscriber_id} row={row} />
      ))}

      {!page.manageable ? null : (
        <section className="card">
          <h2>Register a subscriber</h2>
          <form className="form" aria-label="Register a subscriber" onSubmit={register}>
            <label className="control-label">
              Id{" "}
              <input
                className="form-control"
                type="text"
                value={id}
                onChange={(event) => {
                  setId(event.target.value);
                }}
              />
            </label>
            <FieldProblems problems={problems} field="subscriber_id" />
            <label className="control-label">
              Address it is told at{" "}
              <input
                className="form-control"
                type="url"
                value={endpoint}
                onChange={(event) => {
                  setEndpoint(event.target.value);
                }}
              />
            </label>
            <FieldProblems problems={problems} field="endpoint" />
            <fieldset className="form">
              <legend className="control-label">Told about</legend>
              {page.kinds.map((kind) => (
                <label key={kind} className="control-label">
                  <input
                    type="checkbox"
                    checked={kinds.includes(kind)}
                    onChange={(event) => {
                      setKinds(
                        event.target.checked
                          ? [...kinds, kind]
                          : kinds.filter((one) => one !== kind),
                      );
                    }}
                  />{" "}
                  {kind}
                </label>
              ))}
            </fieldset>
            <FieldProblems problems={problems} field="kinds" />
            <label className="control-label">
              Signing secret{" "}
              <input
                className="form-control"
                type="text"
                autoComplete="off"
                spellCheck={false}
                value={secret}
                onChange={(event) => {
                  setSecret(event.target.value);
                }}
              />
            </label>
            <FieldProblems problems={problems} field="secret" />
            <p className="field-description">
              At least {page.secret_minimum} characters, generated rather than typed, and given to the
              receiver first. It is never shown again.
            </p>
            <div className="form-actions">
              <button type="submit" className="button" disabled={busy}>
                {REGISTER_LABEL}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="card">
        <h2>Arriving from outside</h2>
        <p>{page.inbound.channels_told}</p>
        <div className="grid__scroll">
          <table className="grid__table" aria-label="Channels">
            <thead>
              <tr>
                <th scope="col">Channel</th>
                <th scope="col">Check that it came from the platform</th>
                <th scope="col">How</th>
              </tr>
            </thead>
            <tbody>
              {page.inbound.channels.map((one) => (
                <tr key={one.channel}>
                  <td>{one.channel}</td>
                  <td>
                    {VERIFICATION_LABELS[one.verification]}
                    {one.check === "" ? null : (
                      <>
                        {" "}
                        <code>{one.check}</code>
                      </>
                    )}
                  </td>
                  <td>{one.how}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          {page.inbound.automation_told} <code>{page.inbound.automation_path}</code>
        </p>
      </section>
    </>
  );
}

function WebhookList({ onChanged }: { readonly onChanged: (sentence: string) => void }) {
  const answer = useResource<unknown>(WEBHOOKS_API_PATH);
  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_WEBHOOKS}
      </p>
    );
  }
  const page = readWebhooks(answer.data);
  if (page === null) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK}>
        <p>The answer about webhook subscribers was not in a shape this screen can read.</p>
      </Notice>
    );
  }
  return <WebhookPage page={page} onChanged={onChanged} />;
}

export function Webhooks() {
  // A counter rather than a boolean, so two changes in a row read the list twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [changed, setChanged] = useState<string | null>(null);
  const onChanged = useCallback((sentence: string) => {
    setChanged(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{WEBHOOKS_CRUMB}</p>
      <h1>{WEBHOOKS_HEADING}</h1>
      <p className="lede">{WEBHOOKS_LEDE}</p>
      {changed === null ? null : (
        <p className="note" role="status">
          {changed}
        </p>
      )}
      <WebhookList key={generation} onChanged={onChanged} />
    </article>
  );
}
