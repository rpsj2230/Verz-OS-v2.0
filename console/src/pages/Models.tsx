/**
 * Models and health: the providers this install can use, the failover matrix that says which
 * model answers each level of question and what happens when it fails, and what it cost this
 * month. Everything else is under Advanced.
 *
 * **The layout is the owner's, and the one before it was the reason for this rewrite.** On
 * 2026-09-22 he called the screen "very complicated": about ten tables, jargon (rung, breaker,
 * tier, lane, slot), and his 2026-09-03 screenshot of a failover matrix nowhere on it. So, top to
 * bottom: Providers, one row each with a status in words and its key, test and switch on the row;
 * the Failover matrix exactly as he drew it; Cost this month as one small card; and a closed
 * Advanced section holding the figures, the per-step health, the provider register and the routing
 * settings. What was rejected: a simplified screen that dropped the old tables. Each is an
 * administrator's only way to do something (record a provider's terms, set a level's window, add a
 * residency rule), so they moved and none was deleted. `modelsQuery.ts` holds the arguments.
 *
 * **The matrix and the providers are one answer, the plan the next call makes.** Both are drawn
 * from `GET /models/providers` (`brain.provider_routes`), so a step's provider, role and marker
 * are the executor's own, a switch answers with the plan after it, and the matrix redraws from
 * that answer in the same response. The old Priority and fallback table read `GET /routing/rungs`
 * as well, a second copy of the same steps without their health, and it is gone with its request.
 * Steps are edited on the routing screen behind the matrix's write grant, which is the card's
 * Edit link: a second editor here would be a second copy of that screen's bounds.
 *
 * **Where answers are made sits above the providers, because it decides whether any of them is
 * used.** It is the install's profile, `local` (this server only) or `hosted` (online providers),
 * and until 2026-09-28 only the setup wizard could set it, while every skipped step told the owner
 * to change it "in the setup settings". It is shown to every reader and changed from a
 * confirmation by a reader the API says may, which is the holder of the installation settings
 * over everything (`brain.provider_routes.choose_profile`).
 *
 * **Every row control is confirmed, and drawn only for somebody the API says may use it.**
 * Turning a provider off changes where every department's questions go from the next call, a test
 * spends tokens under the presser's name (`modelsQuery.A_CHECK_SPENDS_TOKENS_SO_IT_IS_CONFIRMED`),
 * and a key replaces the one every question uses, so each goes through
 * `components/ConfirmAction.tsx` with a sentence saying what happens and to what. `editable` and
 * the vault's column are presentation only: the routes refuse without the grant whatever this
 * page drew.
 *
 * **An agent's pinned model is said beside the matrix, not drawn in it** (M5.7.3). A pin belongs
 * to one agent and is set on that agent's Settings tab, where the reader already sees the agent;
 * listing pinned agents here would name agents on a screen whose grant says nothing about which
 * agents a reader may see.
 *
 * **The cost is written in the install's currency and zone**, which the spend report carries
 * (`brain.report_routes.A_FIGURE_SAYS_ITS_CURRENCY_AND_ITS_CLOCK`), as "SGD 288.00" and "6 Mar
 * 2019, 16:00", and never in the browser's zone. An install that chose no currency is shown the
 * amount alone with a link to where it is set, never the code meaning none (found on the owner's
 * install on 2026-09-28 as "XXX 0.00").
 *
 * **Plain words only** (the owner, 2026-09-28): Simple, Medium, Complex, step, provider, model. No
 * rung, ladder, tier, lane or slot is drawn anywhere on the screen, Advanced included, and
 * `tests/models-page.test.tsx` reads the whole rendered page for them.
 *
 * **Each card is loaded, failed or answered on its own.** A reader may hold the models screen and
 * not the usage grant, and the cost card then carries the API's refusal while the providers and
 * the matrix are drawn. Loading, unreachable, refused and unreadable are different sentences in
 * every card.
 *
 * Task ids: M27.2.3, M27.8.8, M5.7.1, M5.7.3, M5.6.4, M5.7.2, M5.2.2, M5.4.3, M5.4.8, M5.5.1
 */

import { useCallback, useMemo, useState, type ReactElement, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource, type Resource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { ProviderKeyForm } from "../components/ProviderKeyForm";
import { ProviderRegister } from "../components/ProviderRegister";
import { RoutingSettings } from "../components/RoutingSettings";
import { Badge } from "../ui/Badge";
import { FailureNotice } from "../ui/FailureNotice";
import { MATRIX_PATH } from "./matrixQuery";
import { probeWords } from "./routingSettingsQuery";
import {
  answerLatencyApiPath,
  answerReading,
  answersWords,
  checkConsequence,
  checkHeading,
  checkQuestion,
  checkServedSentence,
  checkStatusSentence,
  chooseProfileLabel,
  credentialWords,
  DEFAULT_ROLE,
  DO_NOT_TEST,
  exhaustedSentence,
  healthWords,
  KEEP_IT_AS_IT_IS,
  KEY_HELD_IS_THIS_SERVER,
  keyAction,
  keyHeldWords,
  LEVELS_CANNOT_ANSWER,
  levelName,
  matrixRows,
  MODELS_LABEL,
  modelsApiPath,
  NO_PROVIDER,
  NO_STEP_ON_THE_MATRIX,
  otherProfile,
  PROFILE_API_PATH,
  PROFILE_WORDS,
  profileBody,
  profileChosenSentence,
  profileConsequence,
  profileNowSentence,
  profileQuestion,
  profileSentence,
  providerName,
  providerStatus,
  PROVIDERS_API_PATH,
  providerCheckApiPath,
  providerSwitchApiPath,
  readCheck,
  readModels,
  readProviders,
  recentCalls,
  REPLACE_KEY,
  roleWords,
  SEND_THE_TEST,
  spendShares,
  spendThisMonthApiPath,
  stepNumber,
  switchBody,
  switchConsequence,
  SWITCHED_OFF,
  SWITCHED_ON,
  switchedLine,
  switchedSentence,
  switchQuestion,
  TEST,
  TURN_OFF,
  TURN_ON,
  unmeasuredBecause,
  vaultKeyLine,
  WHERE_ANSWERS_ARE_MADE,
  WINDOW_DAYS,
  withoutAModel,
  type ModelsBody,
  type ProviderStatus,
  type ProvidersBody,
  type StepMarker,
} from "./modelsQuery";
import { milliseconds, readServiceLevels, SERVICE_LEVELS_API_PATH } from "./serviceLevelsQuery";
import { SETTINGS_LABEL, SETTINGS_PATH } from "./settingsQuery";
import {
  currencyNotSetHint,
  freshnessInZone,
  moneyWords,
  readSpendReport,
  SPEND_API_PATH,
  SPEND_DIMENSION,
  SPEND_PATH,
} from "./spendQuery";

export const MODELS_LEDE =
  "The providers this install can use, which model answers each level of question and what " +
  "happens when it fails, and what it cost this month.";

export const PROVIDERS_HEADING = "Providers";
export const PROVIDERS_CAPTION = "Every provider this install can use, and whether it is working";

export const FAILOVER_MATRIX = "Failover matrix: what answers, and what happens when it fails";
export const MATRIX_CAPTION = "Each level's steps, in the order a question tries them";
export const MATRIX_LEDE =
  "A question is answered by its level's first step. When a step fails, is too slow or is turned " +
  "away by its provider, the next step is tried.";
export const EDIT = "Edit";
export const PINNED_FIRST =
  "An agent can have its own model pinned on its Settings tab. A pinned model is tried first, and " +
  "the agent's level runs through its steps here if it fails.";

export const COST_THIS_MONTH = "Cost this month";
export const NO_SPEND_THIS_MONTH = "Nothing has been spent this month.";
export const SPEND_NOT_BUILT =
  "The spend report has not been built yet, so there is no cost to show. It is rebuilt on a schedule.";
export const BY_DEPARTMENT = "By department";

export const ADVANCED = "Advanced";
export const FIGURES_HEADING = `Last ${String(WINDOW_DAYS)} days`;
export const PROVIDER_DETAILS = "Provider details";
export const PROVIDER_DETAILS_CAPTION =
  "Every provider, what it is for, who last turned it on or off, and where its key is held";
export const STEP_HEALTH = "Each step's health";
export const STEPS_CAPTION = "Every step on the failover matrix, whether it answers the next call, and its health";

/** The three figures' labels under Advanced. */
export const WITHOUT_A_MODEL = "Answered without a model";
export const P95_ANSWER = "p95 answer";
export const FALLBACKS_FIRED = "Fallbacks fired";

/** Under the fallbacks figure, so the number is read as what it counts. */
export const FALLBACKS_NOTE = "times a question moved to a later step after a failure";

export const NO_REQUESTS = `No request finished in the last ${String(WINDOW_DAYS)} days.`;
export const NO_ANSWER_LANE = "The service-level reading carries no reading for answers.";
export const NOT_MEASURED = "Not measured";

export const SOMETHING_DID_NOT_WORK = "That did not work";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read. The console and the API are probably " +
  "from different releases.";

/** One card's answer: loading, failed, unreadable, or the body. Four sentences, never a blank. */
function Answered<T>({
  busy,
  failure,
  body,
  children,
}: {
  readonly busy: boolean;
  readonly failure: ApiFailure | null;
  readonly body: T | null;
  readonly children: (body: T) => ReactNode;
}) {
  if (busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  if (failure) {
    return <FailureNotice failure={failure} />;
  }
  if (body === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }
  return <>{children(body)}</>;
}

/** The providers answer as every card on the page draws it. */
interface Plan {
  readonly busy: boolean;
  readonly failure: ApiFailure | null;
  readonly body: ProvidersBody | null;
  /** The body as the API sent it, for the two Advanced cards that read it themselves. */
  readonly data: unknown;
}

/**
 * A provider's status as a pill. Each tone is written here as a literal, one per status, and the
 * declared return type is what makes a status added without a pill a type error.
 */
function StatusPill({ status }: { readonly status: ProviderStatus }): ReactElement {
  switch (status.kind) {
    case "working":
      return <Badge label={status.label} tone="positive" />;
    case "resting":
    case "key_refused":
      return <Badge label={status.label} tone="caution" />;
    case "off":
    case "no_key":
    case "server_only":
    case "unused":
      // Neutral, for `ui/Status.tsx`'s reason about an unconfigured connector: a provider nobody
      // has given a key or turned on is a task for whoever set it up, not an incident.
      return <Badge label={status.label} tone="neutral" />;
  }
}

/** A step's marker, drawn only when it will not answer the next call. */
function MarkerPill({ marker }: { readonly marker: StepMarker }): ReactElement {
  switch (marker.kind) {
    case "resting":
    case "no_key":
    case "cannot_call":
    case "key_refused":
      return <Badge label={marker.label} tone="caution" />;
    case "paused":
    case "turned_off":
    case "local_only":
      return <Badge label={marker.label} tone="neutral" />;
  }
}

/** A write this card is about to send, held while its confirmation is open. */
type ProviderAsk =
  | { readonly kind: "switch"; readonly provider: string; readonly name: string; readonly on: boolean }
  | { readonly kind: "check"; readonly provider: string; readonly name: string };

/** What a test came back with. The reply itself is never sent, so it is never drawn. */
function CheckOutcome({ answer, name }: { readonly answer: unknown; readonly name: string }) {
  const check = readCheck(answer);
  if (check === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }
  return (
    <div role="status" aria-label={checkHeading(name)}>
      <p>
        <strong>{checkHeading(name)}</strong>
      </p>
      <p>{check.told}</p>
      {check.answered ? <p className="note">{checkServedSentence(check)}</p> : null}
      {!check.answered && check.status !== null ? (
        <p className="note">{checkStatusSentence(check.status)}</p>
      ) : null}
      <p className="note">
        Reference <code>{check.trace_id}</code>
      </p>
    </div>
  );
}

function ProvidersTable({
  body,
  busy,
  keyFor,
  onAsk,
  onKey,
  onKeySaved,
}: {
  readonly body: ProvidersBody;
  readonly busy: boolean;
  readonly keyFor: string | null;
  readonly onAsk: (asked: ProviderAsk) => void;
  readonly onKey: (provider: string | null) => void;
  readonly onKeySaved: (sentence: string) => void;
}) {
  if (body.providers.length === 0) {
    return <p className="note">{NO_PROVIDER}</p>;
  }
  // A key action for a reader the API sent the vault's column to, which is a reader who may
  // manage credentials; for anybody else there is no key button rather than one that fails.
  const keys = body.providers.some((one) => one.credential !== null);
  const actions = keys || body.editable;
  return (
    <div className="grid__scroll">
      <table className="grid__table">
        <caption className="grid__caption">{PROVIDERS_CAPTION}</caption>
        <thead>
          <tr>
            <th scope="col">Provider</th>
            <th scope="col">Status</th>
            {actions ? <th scope="col">Actions</th> : null}
          </tr>
        </thead>
        <tbody>
          {body.providers.map((row) => {
            const name = providerName(row.provider, body.providers);
            const key = keyAction(row);
            return [
              <tr key={row.provider}>
                <td>{name}</td>
                <td>
                  <StatusPill status={providerStatus(row, body.rungs, body.profile)} />
                  {vaultKeyLine(row) === null ? null : <p className="note">{vaultKeyLine(row)}</p>}
                </td>
                {actions ? (
                  <td>
                    {/* A block inside the cell, because a cell that is itself a flex box stops being one. */}
                    <div className="row-actions">
                      {row.credential === null ? null : (
                        <button
                          type="button"
                          className="button"
                          disabled={busy}
                          aria-expanded={keyFor === row.provider}
                          aria-label={`${key}: ${name}`}
                          onClick={() => {
                            onKey(keyFor === row.provider ? null : row.provider);
                          }}
                        >
                          {key}
                        </button>
                      )}
                      {body.editable ? (
                        <>
                          <button
                            type="button"
                            className="button"
                            disabled={busy}
                            aria-label={`${TEST}: ${name}`}
                            onClick={() => {
                              onAsk({ kind: "check", provider: row.provider, name });
                            }}
                          >
                            {TEST}
                          </button>
                          <button
                            type="button"
                            className="button"
                            disabled={busy}
                            aria-label={`${row.switched_on ? TURN_OFF : TURN_ON}: ${name}`}
                            onClick={() => {
                              onAsk({ kind: "switch", provider: row.provider, name, on: !row.switched_on });
                            }}
                          >
                            {row.switched_on ? TURN_OFF : TURN_ON}
                          </button>
                        </>
                      ) : null}
                    </div>
                  </td>
                ) : null}
              </tr>,
              keyFor === row.provider && row.credential !== null ? (
                <tr key={`${row.provider}-key`}>
                  <td colSpan={3}>
                    <ProviderKeyForm
                      row={row}
                      name={name}
                      held={key === REPLACE_KEY}
                      onSaved={onKeySaved}
                      onClose={() => {
                        onKey(null);
                      }}
                    />
                  </td>
                </tr>
              ) : null,
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}

function ProvidersCard({ plan, onPlan }: { readonly plan: Plan; readonly onPlan: (plan: unknown) => void }) {
  const [asked, setAsked] = useState<ProviderAsk | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const [checked, setChecked] = useState<{ readonly answer: unknown; readonly name: string } | null>(null);
  const [keyFor, setKeyFor] = useState<string | null>(null);

  const send = useCallback(
    (pending: ProviderAsk) => {
      setBusy(true);
      void (async () => {
        if (pending.kind === "switch") {
          const result = await request<unknown>(providerSwitchApiPath(pending.provider), {
            method: "PUT",
            body: switchBody(pending.on),
          });
          setBusy(false);
          setAsked(null);
          if (!result.ok) {
            setFailure(result.failure);
            return;
          }
          setFailure(null);
          onPlan(result.data);
          setTold(switchedSentence(pending.name, pending.on));
          return;
        }
        const result = await request<unknown>(providerCheckApiPath(pending.provider), { method: "POST" });
        setBusy(false);
        setAsked(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        setChecked({ answer: result.data, name: pending.name });
      })();
    },
    [onPlan],
  );

  return (
    <section className="card" aria-labelledby="models-providers">
      <h2 id="models-providers">{PROVIDERS_HEADING}</h2>
      <Answered busy={plan.busy} failure={plan.failure} body={plan.body}>
        {(body) => (
          <>
            <ProvidersTable
              body={body}
              busy={busy}
              keyFor={keyFor}
              onAsk={(one) => {
                setFailure(null);
                setTold(null);
                setChecked(null);
                setAsked(one);
              }}
              onKey={(provider) => {
                setTold(null);
                setKeyFor(provider);
              }}
              onKeySaved={(sentence) => {
                setKeyFor(null);
                setTold(sentence);
                // Read the plan again, so the row's status and button are the vault's new answer.
                void (async () => {
                  const again = await request<unknown>(PROVIDERS_API_PATH);
                  if (again.ok) {
                    onPlan(again.data);
                  }
                })();
              }}
            />
            {body.vault === null || body.vault === "ready" || body.vault_told === null ? null : (
              <p className="note">{body.vault_told}</p>
            )}
            {asked === null ? null : (
              <ConfirmAction
                question={asked.kind === "switch" ? switchQuestion(asked.name, asked.on) : checkQuestion(asked.name)}
                consequence={
                  asked.kind === "switch" ? switchConsequence(asked.name, asked.on) : checkConsequence(asked.name)
                }
                confirmLabel={asked.kind === "switch" ? (asked.on ? TURN_ON : TURN_OFF) : SEND_THE_TEST}
                cancelLabel={asked.kind === "switch" ? KEEP_IT_AS_IT_IS : DO_NOT_TEST}
                busy={busy}
                onConfirm={() => {
                  send(asked);
                }}
                onCancel={() => {
                  setAsked(null);
                }}
              />
            )}
            {told === null ? null : (
              <p className="note" role="status">
                {told}
              </p>
            )}
            {failure === null ? null : <FailureNotice failure={failure} />}
            {checked === null ? null : <CheckOutcome answer={checked.answer} name={checked.name} />}
          </>
        )}
      </Answered>
    </section>
  );
}

/**
 * Where answers are made: the install's profile, shown to every reader of the screen and changed
 * only by a reader the API says may, from a confirmation. See
 * `brain.provider_routes.WHERE_ANSWERS_ARE_MADE_IS_AN_INSTALLATION_SETTING_AND_NOT_A_SWITCH`.
 */
function WhereAnswersAreMade({ plan, onPlan }: { readonly plan: Plan; readonly onPlan: (plan: unknown) => void }) {
  const [asked, setAsked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);

  const send = (pending: string) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(PROFILE_API_PATH, { method: "PUT", body: profileBody(pending) });
      setBusy(false);
      setAsked(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onPlan(result.data);
      setTold(profileChosenSentence(pending));
    })();
  };

  return (
    <section className="card" aria-labelledby="models-where">
      <h2 id="models-where">{WHERE_ANSWERS_ARE_MADE}</h2>
      <Answered busy={plan.busy} failure={plan.failure} body={plan.body}>
        {(body) => {
          const target = otherProfile(body.profile);
          return (
            <>
              <p>
                <strong>{PROFILE_WORDS[body.profile] ?? body.profile}</strong>. {profileNowSentence(body.profile)}
              </p>
              {body.profile_editable ? (
                <p>
                  <button
                    type="button"
                    className="button"
                    disabled={busy || asked !== null}
                    onClick={() => {
                      setFailure(null);
                      setTold(null);
                      setAsked(target);
                    }}
                  >
                    {chooseProfileLabel(target)}
                  </button>
                </p>
              ) : null}
              {asked === null ? null : (
                <ConfirmAction
                  question={profileQuestion(asked)}
                  consequence={profileConsequence(asked)}
                  confirmLabel={chooseProfileLabel(asked)}
                  cancelLabel={KEEP_IT_AS_IT_IS}
                  busy={busy}
                  onConfirm={() => {
                    send(asked);
                  }}
                  onCancel={() => {
                    setAsked(null);
                  }}
                />
              )}
              {told === null ? null : (
                <p className="note" role="status">
                  {told}
                </p>
              )}
              {failure === null ? null : <FailureNotice failure={failure} />}
            </>
          );
        }}
      </Answered>
    </section>
  );
}

function FailoverMatrix({ plan }: { readonly plan: Plan }) {
  return (
    <section className="card" aria-labelledby="models-matrix">
      <div className="card__heading">
        <h2 id="models-matrix">{FAILOVER_MATRIX}</h2>
        <Link to={MATRIX_PATH}>{EDIT}</Link>
      </div>
      <p className="note">{MATRIX_LEDE}</p>
      <Answered busy={plan.busy} failure={plan.failure} body={plan.body}>
        {(body) => {
          const rows = matrixRows(body);
          if (rows.length === 0) {
            return <p className="note">{NO_STEP_ON_THE_MATRIX}</p>;
          }
          return (
            <>
              {body.exhausted_tiers.length === 0 ? null : (
                // The notice's appearance without `Notice`'s `role="status"`: this is drawn with the
                // answer rather than announced as a change to it, and a live region present from the
                // first render reads to a screen reader as a page still telling somebody something.
                <div className="notice" aria-label={LEVELS_CANNOT_ANSWER}>
                  <p className="notice__title">{LEVELS_CANNOT_ANSWER}</p>
                  <div className="notice__body">
                    {body.exhausted_tiers.map((tier) => (
                      <p key={tier}>{exhaustedSentence(tier)}</p>
                    ))}
                  </div>
                </div>
              )}
              <div className="grid__scroll">
                <table className="grid__table matrix">
                  <caption className="grid__caption">{MATRIX_CAPTION}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Complexity</th>
                      <th scope="col">Step</th>
                      <th scope="col">Provider</th>
                      <th scope="col">Model</th>
                      <th scope="col">Role</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.key} className={row.level === null ? undefined : "matrix__first"}>
                        <td className="matrix__level">{row.level ?? ""}</td>
                        <td className="matrix__step">{row.step === null ? "" : String(row.step)}</td>
                        <td>{row.provider}</td>
                        <td>{row.model === "" ? null : <code>{row.model}</code>}</td>
                        <td>
                          {row.role === DEFAULT_ROLE ? (
                            <Badge label={roleWords(row.role)} tone="caution" />
                          ) : (
                            <span className="note">{roleWords(row.role)}</span>
                          )}
                          {row.marker === null ? null : (
                            <>
                              {" "}
                              <MarkerPill marker={row.marker} />
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          );
        }}
      </Answered>
      <p className="note">{PINNED_FIRST}</p>
    </section>
  );
}

function CostThisMonth({ spend }: { readonly spend: Resource<unknown> }) {
  return (
    <section className="card" aria-labelledby="models-cost">
      <h2 id="models-cost">{COST_THIS_MONTH}</h2>
      <Answered busy={spend.busy} failure={spend.failure} body={spend.data === null ? null : readSpendReport(spend.data)}>
        {(report) => {
          if (!report.built || report.total_minor === null) {
            return <p className="note">{SPEND_NOT_BUILT}</p>;
          }
          const shares = spendShares(report);
          const unset = currencyNotSetHint(report.currency);
          return (
            <>
              <p className="figure">{moneyWords(report.total_minor, report.currency)}</p>
              {unset === null ? null : (
                <p className="note">
                  {unset} <Link to={SETTINGS_PATH}>{SETTINGS_LABEL}</Link>
                </p>
              )}
              <p className="note">{freshnessInZone(report)}</p>
              {shares.length === 0 ? (
                <p className="note">{NO_SPEND_THIS_MONTH}</p>
              ) : (
                <dl className="fields" aria-label={BY_DEPARTMENT}>
                  {shares.map((line) => (
                    <div className="fields__row" key={line.key}>
                      <dt>{line.key}</dt>
                      <dd>{moneyWords(line.costMinor, report.currency)}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <p>
                <Link to={SPEND_PATH}>Spend</Link>
              </p>
            </>
          );
        }}
      </Answered>
    </section>
  );
}

function Figures({ models, latency }: { readonly models: ModelsBody; readonly latency: Resource<unknown> }) {
  const share = withoutAModel(models.lanes);
  // Named by the API only while the ledger cannot fill the count, and then the number beside it
  // would be a zero nothing measured, so the sentence replaces the number rather than joining it.
  const fallbacksUnmeasured = unmeasuredBecause(models, "fallback_count");
  return (
    <section aria-labelledby="models-figures">
      <h3 id="models-figures">{FIGURES_HEADING}</h3>
      <dl className="fields">
        <div className="fields__row">
          <dt>{WITHOUT_A_MODEL}</dt>
          <dd>{share === null ? <span className="note">{NO_REQUESTS}</span> : <span>{share}</span>}</dd>
        </div>
        <div className="fields__row">
          <dt>{P95_ANSWER}</dt>
          <dd>
            <Answered
              busy={latency.busy}
              failure={latency.failure}
              body={latency.data === null ? null : readServiceLevels(latency.data)}
            >
              {(reading) => {
                const answer = answerReading(reading.lanes);
                if (answer === null) {
                  return <span className="note">{NO_ANSWER_LANE}</span>;
                }
                return (
                  <>
                    <span>{milliseconds(answer.p95_ms)}</span>
                    <p className="note">target {milliseconds(answer.objective_p95_ms)}</p>
                  </>
                );
              }}
            </Answered>
          </dd>
        </div>
        <div className="fields__row">
          <dt>{FALLBACKS_FIRED}</dt>
          <dd>
            {fallbacksUnmeasured === null ? (
              <>
                <span>{String(models.fallbacks_fired)}</span>
                <p className="note">{FALLBACKS_NOTE}</p>
              </>
            ) : (
              <>
                <span>{NOT_MEASURED}</span>
                <p className="note">{fallbacksUnmeasured}</p>
              </>
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function ProviderDetails({ body }: { readonly body: ProvidersBody }) {
  // The vault's column only for a reader the API sent a credential to; for anybody else there is
  // no column rather than an empty one, which would say there is something they are not shown.
  const vault = body.providers.some((one) => one.credential !== null);
  return (
    <section aria-labelledby="models-provider-details">
      <h3 id="models-provider-details">{PROVIDER_DETAILS}</h3>
      <p className="note">{profileSentence(body.profile)}</p>
      <div className="grid__scroll">
        <table className="grid__table">
          <caption className="grid__caption">{PROVIDER_DETAILS_CAPTION}</caption>
          <thead>
            <tr>
              <th scope="col">Provider</th>
              <th scope="col">What it is for</th>
              <th scope="col">On or off</th>
              <th scope="col">Key held here</th>
              {vault ? <th scope="col">In the vault</th> : null}
            </tr>
          </thead>
          <tbody>
            {body.providers.map((row) => {
              const line = switchedLine(row);
              return (
                <tr key={row.provider}>
                  <td>
                    {providerName(row.provider, body.providers)} <code>{row.provider}</code>
                  </td>
                  <td>{row.description}</td>
                  <td>
                    {row.switched_on ? SWITCHED_ON : SWITCHED_OFF}
                    {line === null ? null : <p className="note">{line}</p>}
                  </td>
                  <td>{keyHeldWords(row.key_held)}</td>
                  {vault ? <td>{row.credential === null ? "-" : credentialWords(row.credential)}</td> : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note">{KEY_HELD_IS_THIS_SERVER}</p>
      {body.vault_told === null ? null : <p className="note">{body.vault_told}</p>}
    </section>
  );
}

function StepHealth({ body }: { readonly body: ProvidersBody }) {
  return (
    <section aria-labelledby="models-step-health">
      <h3 id="models-step-health">{STEP_HEALTH}</h3>
      {body.rungs.length === 0 ? (
        <p className="note">{NO_STEP_ON_THE_MATRIX}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{STEPS_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">Level</th>
                <th scope="col">Step</th>
                <th scope="col">Model</th>
                <th scope="col">Provider</th>
                <th scope="col">Answers now</th>
                <th scope="col">Health</th>
                <th scope="col">Recent calls</th>
                <th scope="col">Background checks</th>
              </tr>
            </thead>
            <tbody>
              {body.rungs.map((step) => (
                <tr key={step.rung_id}>
                  <td>{levelName(step.tier)}</td>
                  <td>{String(stepNumber(step, body.rungs))}</td>
                  <td>
                    <code>{step.model}</code>
                  </td>
                  <td>{providerName(step.provider, body.providers)}</td>
                  <td>{answersWords(step)}</td>
                  <td>{healthWords(step)}</td>
                  <td>{recentCalls(step)}</td>
                  <td>{probeWords(step.probes_seen, step.probes_failed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Advanced({
  models,
  latency,
  plan,
  onPlan,
}: {
  readonly models: ModelsBody;
  readonly latency: Resource<unknown>;
  readonly plan: Plan;
  readonly onPlan: (plan: unknown) => void;
}) {
  const noModel = unmeasuredBecause(models, "model");
  const noProvider = unmeasuredBecause(models, "provider");
  return (
    <details className="card advanced">
      <summary>
        <h2 id="models-advanced">{ADVANCED}</h2>
      </summary>
      <Figures models={models} latency={latency} />
      <Answered busy={plan.busy} failure={plan.failure} body={plan.body}>
        {(body) => (
          <>
            <ProviderDetails body={body} />
            <StepHealth body={body} />
            <ProviderRegister data={plan.data} onWritten={onPlan} />
            <RoutingSettings data={plan.data} onWritten={onPlan} />
          </>
        )}
      </Answered>
      {noModel === null ? null : <p className="note">{noModel}</p>}
      {noProvider === null ? null : <p className="note">{noProvider}</p>}
    </details>
  );
}

/** The cards that need the models route's answer, and the three routes they ask beside it. */
function ModelsAnswer({ models }: { readonly models: ModelsBody }) {
  const answer = useResource<unknown>(PROVIDERS_API_PATH);
  // The plan a write answered with, which replaces the one the page first read.
  const [written, setWritten] = useState<unknown>(null);
  const latency = useResource<unknown>(answerLatencyApiPath(SERVICE_LEVELS_API_PATH));
  // Computed once per mount, so the address does not change under the effect that fetches it.
  const month = useMemo(() => spendThisMonthApiPath(SPEND_API_PATH, SPEND_DIMENSION, new Date()), []);
  const spend = useResource<unknown>(month);

  const data = written !== null ? written : answer.data;
  const plan: Plan = {
    busy: written === null && answer.busy,
    failure: written === null ? answer.failure : null,
    body: data === null ? null : readProviders(data),
    data,
  };
  const onPlan = useCallback((next: unknown) => {
    setWritten(next);
  }, []);

  return (
    <>
      <WhereAnswersAreMade plan={plan} onPlan={onPlan} />
      <ProvidersCard plan={plan} onPlan={onPlan} />
      <FailoverMatrix plan={plan} />
      <CostThisMonth spend={spend} />
      <Advanced models={models} latency={latency} plan={plan} onPlan={onPlan} />
    </>
  );
}

export function Models() {
  const answer = useResource<unknown>(modelsApiPath());

  return (
    <article className="page">
      <h1>{MODELS_LABEL}</h1>
      <p className="lede">{MODELS_LEDE}</p>
      <Answered
        busy={answer.busy}
        failure={answer.failure}
        body={answer.data === null ? null : readModels(answer.data)}
      >
        {(models) => <ModelsAnswer models={models} />}
      </Answered>
    </article>
  );
}
