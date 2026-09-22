/**
 * Models and health: which model answers each tier, in what order the chain falls back, the
 * providers behind it with each rung's measured health, and the two things an administrator can do
 * about a provider from here.
 *
 * `docs/screens.html` SCREEN 11 is the design of record and this page is its layout: the bar with
 * the window and Edit routing, four figures, the Priority and fallback table, and Provider health
 * beside Spend by department. `modelsQuery.ts` holds the arguments; the facts are in
 * `brain.operate_routes`, `brain.provider_routes`, `brain.routing_routes`, `brain.report_routes`
 * and `brain.console.operate`, which decides whether this screen's own figures open at all.
 *
 * **Provider health draws the plan the next call makes, and not a picture of one.** The card asks
 * `GET /models/providers`, which is the executor's own plan: which rungs answer, the API's sentence
 * for each one left out, and each breaker as the attempts left it. A rung nothing has called is
 * drawn as not called yet and never as healthy, which is
 * `modelsQuery.AN_UNCALLED_RUNG_IS_NOT_A_HEALTHY_ONE`, and a tier whose every rung is resting is a
 * notice at the top of the card rather than a row somebody has to spot. The design's green bars
 * are not drawn: a bar needs a rate over a window, and the route sends counts of recent calls,
 * which are drawn as the counts they are.
 *
 * **Two controls per provider, both confirmed, both drawn only for somebody the API says may use
 * them.** Switching a provider off changes where every department's questions go from the next
 * call, and a check spends tokens under the presser's name, so each goes through
 * `components/ConfirmAction.tsx` with a sentence saying what happens and to what. `editable` is
 * presentation only: the route refuses both writes without the matrix's write grant over
 * everything, whatever this page drew. A switch answers with the plan after it, and the card is
 * redrawn from that answer rather than from what this page expected, so a provider switched off is
 * seen leaving the chain in the same response.
 *
 * **Edit routing is a link, and it is the design's.** The chain's four operational numbers are
 * edited on the routing screen, behind the matrix's write grant, where the form checks them
 * against the route's own bounds. A second editor here would be a second copy of those bounds and
 * a second place a rung could be taken out of rotation without the first screen knowing.
 *
 * **Each card is loaded, failed or answered on its own.** A reader may hold the models screen and
 * not the usage grant, and the spend card then carries the API's refusal while the chain is
 * drawn; a single spinner or a single failure for the page would hide four answers behind the
 * one that did not come back. Loading, unreachable, refused and unreadable are different
 * sentences in every card.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet of its
 * own. `matrixQuery.ts` is imported for its path and its reader, and its only imports of the form
 * library are types, which a build erases.
 *
 * **The provider register sits under the health card** (`components/ProviderRegister.tsx`): each provider's
 * processing region, retention and training terms, agreement and lane overrides, what it has been
 * sent by category with counts, a provider added with its key, and the register downloaded.
 *
 * **Routing settings sit under the register** (`components/RoutingSettings.tsx`): each tier's window
 * and headroom as the router reads them, the residency constraints attached to scopes, and the
 * chain-depth alerts of the last day, from the same providers answer. Each rung's probes, from the
 * worker's prober, are drawn beside its recent calls.
 *
 * Task ids: M27.2.3, M27.8.8, M5.6.4, M5.7.2, M5.2.2, M5.4.3, M5.4.8, M5.5.1
 */

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource, type Resource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Chip } from "../ui/Chip";
import { FailureNotice } from "../ui/FailureNotice";
import { chainApiPath, MATRIX_PATH, readMatrixPage, type RungRow } from "./matrixQuery";
import { ProviderKeyForm } from "../components/ProviderKeyForm";
import { ProviderRegister } from "../components/ProviderRegister";
import { RoutingSettings } from "../components/RoutingSettings";
import { probeWords } from "./routingSettingsQuery";
import {
  answerLatencyApiPath,
  answerReading,
  answersWords,
  CHECK,
  checkConsequence,
  checkHeading,
  checkQuestion,
  checkServedSentence,
  checkStatusSentence,
  chainRows,
  credentialWords,
  DO_NOT_CHECK,
  exhaustedSentence,
  healthWords,
  KEEP_IT_AS_IT_IS,
  KEY_HELD_IS_THIS_SERVER,
  keyHeldWords,
  MODELS_LABEL,
  modelsApiPath,
  NO_MODEL_TIER,
  NO_PROVIDER,
  NO_RUNG_ON_THE_LADDER,
  profileSentence,
  PROVIDERS_API_PATH,
  providerCheckApiPath,
  providerSwitchApiPath,
  readCheck,
  readModels,
  readProviders,
  recentCalls,
  SEND_THE_CHECK,
  spendShares,
  spendSinceApiPath,
  SWITCH_OFF,
  SWITCH_ON,
  switchBody,
  switchConsequence,
  SWITCHED_OFF,
  SWITCHED_ON,
  switchedLine,
  switchedSentence,
  switchQuestion,
  TIERS_CANNOT_ANSWER,
  unmeasuredBecause,
  WINDOW_DAYS,
  withoutAModel,
  type ModelsBody,
  type ProvidersBody,
} from "./modelsQuery";
import { milliseconds, readServiceLevels, SERVICE_LEVELS_API_PATH } from "./serviceLevelsQuery";
import {
  freshnessLine,
  majorUnits,
  readSpendReport,
  SPEND_API_PATH,
  SPEND_DIMENSION,
  SPEND_PATH,
} from "./spendQuery";

export const MODELS_LEDE =
  "Which model answers each tier and what the chain falls back to, the providers behind it with " +
  "each rung's health, and what this install measures about them.";

/** The window, in the design's words. */
export const WINDOW_LABEL = `Last ${String(WINDOW_DAYS)} days`;

/** The four figures' labels, in the design's words. */
export const WITHOUT_A_MODEL = "Answered without a model";
export const P95_ANSWER = "p95 answer";
export const FALLBACKS_FIRED = "Fallbacks fired";
export const COST = `Cost ${String(WINDOW_DAYS)}d`;

/** Under the fallbacks figure, so the number is read as what it counts. */
export const FALLBACKS_NOTE = "times a request moved to a later rung after a failure";

export const PRIORITY_AND_FALLBACK = "Priority and fallback";
export const PROVIDER_HEALTH = "Provider health";
export const SPEND_BY_DEPARTMENT = "Spend by department";
export const EDIT_ROUTING = "Edit routing";

export const PROVIDERS_CAPTION =
  "Every provider this install can call, whether it is switched on, and whether a key is held";
export const RUNGS_CAPTION =
  "Every rung on the routing ladder, whether it answers the next call, and its health";

export const NO_REQUESTS = `No request finished in the last ${String(WINDOW_DAYS)} days.`;
export const NO_ANSWER_LANE = "The service-level reading carries no answer lane.";
export const NOT_MEASURED = "Not measured";
export const NO_SPEND = `No spend is recorded in the last ${String(WINDOW_DAYS)} days.`;
export const SPEND_NOT_BUILT =
  "The spend report has not been built yet, so there is no cost to show. It is rebuilt on a schedule.";
export const NO_RUNG = "Nothing configured";
export const NO_MODEL = "no model";
export const OUT_OF_ROTATION = "out of rotation";
export const MORE_RUNGS = "This page came back full, so there are more rungs than it shows.";

/** Under the spend bars, so a bar is not read as a share of a budget. */
export const SHARE_OF_THE_COST =
  "Each bar is that department's share of the cost shown above, not of its budget.";

/** Where the design's Budget and p95 columns would be, said once. */
export const NO_BUDGET_OR_LATENCY_PER_TIER =
  "The design gives each row a budget and a p95. This install keeps budgets per company, " +
  "department and person rather than per tier, and measures latency per lane rather than per " +
  "tier, so neither is shown here. The p95 for answers is above, and budgets are on the Spend " +
  "screen.";

export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
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

/** A request that did not come back, with the heading that says which way it failed. */
/** One rung in a table cell: the model, its provider, and whether it is in rotation. */
function RungCell({ rung }: { readonly rung: RungRow | undefined }) {
  if (rung === undefined) {
    return <span className="note">-</span>;
  }
  return (
    <>
      <code>{rung.model}</code> <Chip label={rung.provider} />
      {rung.enabled ? null : (
        <>
          {" "}
          <Chip label={OUT_OF_ROTATION} />
        </>
      )}
    </>
  );
}

/** The three answers the cards below the models route share, asked once for the page. */
interface Borrowed {
  readonly matrix: Resource<unknown>;
  readonly latency: Resource<unknown>;
  readonly spend: Resource<unknown>;
}

function Figures({ models, borrowed }: { readonly models: ModelsBody; readonly borrowed: Borrowed }) {
  const share = withoutAModel(models.lanes);
  // Named by the API only while the ledger cannot fill the count, and then the number beside it
  // would be a zero nothing measured, so the sentence replaces the number rather than joining it.
  const fallbacksUnmeasured = unmeasuredBecause(models, "fallback_count");
  const { latency, spend } = borrowed;

  return (
    <section className="card" aria-label="Figures">
      <dl className="fields">
        <div className="fields__row">
          <dt>{WITHOUT_A_MODEL}</dt>
          <dd>
            {share === null ? <span className="note">{NO_REQUESTS}</span> : <span>{share}</span>}
            <p className="note">fast lane</p>
          </dd>
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
        <div className="fields__row">
          <dt>{COST}</dt>
          <dd>
            <Answered
              busy={spend.busy}
              failure={spend.failure}
              body={spend.data === null ? null : readSpendReport(spend.data)}
            >
              {(report) =>
                report.built && report.total_minor !== null ? (
                  <>
                    <span>{majorUnits(report.total_minor)}</span>
                    <p className="note">{freshnessLine(report)}</p>
                  </>
                ) : (
                  <span className="note">{SPEND_NOT_BUILT}</span>
                )
              }
            </Answered>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function PriorityAndFallback({
  models,
  matrix,
}: {
  readonly models: ModelsBody;
  readonly matrix: Resource<unknown>;
}) {
  const noModel = unmeasuredBecause(models, "model");

  return (
    <section className="card" aria-labelledby="models-chain">
      <h2 id="models-chain">{PRIORITY_AND_FALLBACK}</h2>
      <Answered
        busy={matrix.busy}
        failure={matrix.failure}
        body={matrix.data === null ? null : readMatrixPage(matrix.data)}
      >
        {(page) => {
          const rows = chainRows(models.tiers, page.rungs);
          const later = rows.some((row) => row.rungs.length > 3);
          return (
            <>
              <div className="grid__scroll">
                <table className="grid__table">
                  <caption className="grid__caption">
                    Each tier&apos;s chain, in the order a request tries it
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Tier</th>
                      <th scope="col">What it handles</th>
                      <th scope="col">Primary</th>
                      <th scope="col">Fallback 1</th>
                      <th scope="col">Fallback 2</th>
                      {later ? <th scope="col">Later fallbacks</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.tier}>
                        <td>
                          <code>{row.tier}</code>
                        </td>
                        <td>{row.handles}</td>
                        <td>
                          {row.rungs.length > 0 ? (
                            <RungCell rung={row.rungs[0]} />
                          ) : row.tier === NO_MODEL_TIER ? (
                            <Chip label={NO_MODEL} />
                          ) : (
                            <span className="note">{NO_RUNG}</span>
                          )}
                        </td>
                        <td>
                          <RungCell rung={row.rungs[1]} />
                        </td>
                        <td>
                          <RungCell rung={row.rungs[2]} />
                        </td>
                        {later ? (
                          <td>
                            {row.rungs.slice(3).map((rung) => (
                              <p key={rung.id}>
                                <RungCell rung={rung} />
                              </p>
                            ))}
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {page.truncated ? <p className="note">{MORE_RUNGS}</p> : null}
            </>
          );
        }}
      </Answered>
      <p className="note">{NO_BUDGET_OR_LATENCY_PER_TIER}</p>
      {noModel === null ? null : <p className="note">{noModel}</p>}
    </section>
  );
}

/** A write this card is about to send, held while its confirmation is open. */
type ProviderAsk =
  | { readonly kind: "switch"; readonly provider: string; readonly on: boolean }
  | { readonly kind: "check"; readonly provider: string };

function ProvidersTable({
  body,
  busy,
  onAsk,
}: {
  readonly body: ProvidersBody;
  readonly busy: boolean;
  readonly onAsk: (asked: ProviderAsk) => void;
}) {
  if (body.providers.length === 0) {
    return <p className="note">{NO_PROVIDER}</p>;
  }
  // The vault's column is drawn only for a reader the API sent a credential to, which is a reader
  // who may manage credentials; for anybody else there is no column rather than an empty one.
  const vault = body.providers.some((one) => one.credential !== null);
  return (
    <>
      <div className="grid__scroll">
        <table className="grid__table">
          <caption className="grid__caption">{PROVIDERS_CAPTION}</caption>
          <thead>
            <tr>
              <th scope="col">Provider</th>
              <th scope="col">What it is for</th>
              <th scope="col">Switched</th>
              <th scope="col">Key held</th>
              {vault ? <th scope="col">In the vault</th> : null}
              {body.editable ? <th scope="col">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {body.providers.map((row) => {
              const line = switchedLine(row);
              return (
                <tr key={row.provider}>
                  <td>
                    <code>{row.provider}</code>
                  </td>
                  <td>{row.description}</td>
                  <td>
                    {row.switched_on ? SWITCHED_ON : SWITCHED_OFF}
                    {line === null ? null : <p className="note">{line}</p>}
                  </td>
                  <td>{keyHeldWords(row.key_held)}</td>
                  {vault ? <td>{row.credential === null ? "-" : credentialWords(row.credential)}</td> : null}
                  {body.editable ? (
                    <td>
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        aria-label={`${row.switched_on ? SWITCH_OFF : SWITCH_ON}: ${row.provider}`}
                        onClick={() => {
                          onAsk({ kind: "switch", provider: row.provider, on: !row.switched_on });
                        }}
                      >
                        {row.switched_on ? SWITCH_OFF : SWITCH_ON}
                      </button>{" "}
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        aria-label={`${CHECK}: ${row.provider}`}
                        onClick={() => {
                          onAsk({ kind: "check", provider: row.provider });
                        }}
                      >
                        {CHECK}
                      </button>
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note">{KEY_HELD_IS_THIS_SERVER}</p>
      {body.vault_told === null ? null : <p className="note">{body.vault_told}</p>}
    </>
  );
}

function RungsTable({ body }: { readonly body: ProvidersBody }) {
  if (body.rungs.length === 0) {
    return <p className="note">{NO_RUNG_ON_THE_LADDER}</p>;
  }
  return (
    <div className="grid__scroll">
      <table className="grid__table">
        <caption className="grid__caption">{RUNGS_CAPTION}</caption>
        <thead>
          <tr>
            <th scope="col">Tier</th>
            <th scope="col">Position</th>
            <th scope="col">Model</th>
            <th scope="col">Provider</th>
            <th scope="col">Answers now</th>
            <th scope="col">Health</th>
            <th scope="col">Recent calls</th>
            <th scope="col">Probes</th>
          </tr>
        </thead>
        <tbody>
          {body.rungs.map((rung) => (
            <tr key={rung.rung_id}>
              <td>
                <code>{rung.tier}</code>
              </td>
              <td>{String(rung.position)}</td>
              <td>
                <code>{rung.model}</code>
              </td>
              <td>
                <code>{rung.provider}</code>
              </td>
              <td>{answersWords(rung)}</td>
              <td>{healthWords(rung)}</td>
              <td>{recentCalls(rung)}</td>
              <td>{probeWords(rung.probes_seen, rung.probes_failed)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** What a check came back with. The reply itself is never sent, so it is never drawn. */
function CheckOutcome({ answer }: { readonly answer: unknown }) {
  const check = readCheck(answer);
  if (check === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }
  return (
    <div role="status" aria-label={checkHeading(check.provider)}>
      <p>
        <strong>{checkHeading(check.provider)}</strong>
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

function ProviderHealth({ models }: { readonly models: ModelsBody }) {
  const answer = useResource<unknown>(PROVIDERS_API_PATH);
  // The plan a switch answered with, which replaces the one this card first read.
  const [written, setWritten] = useState<unknown>(null);
  const [asked, setAsked] = useState<ProviderAsk | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [switched, setSwitched] = useState<string | null>(null);
  const [checked, setChecked] = useState<unknown>(null);
  const unmeasured = unmeasuredBecause(models, "provider");

  const send = useCallback((pending: ProviderAsk) => {
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
        setWritten(result.data);
        setSwitched(switchedSentence(pending.provider, pending.on));
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
      setChecked(result.data);
    })();
  }, []);

  const drawn = written !== null ? readProviders(written) : answer.data === null ? null : readProviders(answer.data);

  return (
    <section className="card" aria-labelledby="models-providers">
      <h2 id="models-providers">{PROVIDER_HEALTH}</h2>
      <Answered busy={written === null && answer.busy} failure={written === null ? answer.failure : null} body={drawn}>
        {(body) => (
          <>
            <p>{profileSentence(body.profile)}</p>
            {body.exhausted_tiers.length === 0 ? null : (
              // The notice's appearance without `Notice`'s `role="status"`: this is drawn with the
              // answer rather than announced as a change to it, and a live region present from the
              // first render reads to a screen reader, and to the phone-width harness, as a page
              // still telling somebody something is in progress.
              <div className="notice" aria-label={TIERS_CANNOT_ANSWER}>
                <p className="notice__title">{TIERS_CANNOT_ANSWER}</p>
                <div className="notice__body">
                  {body.exhausted_tiers.map((tier) => (
                    <p key={tier}>{exhaustedSentence(tier)}</p>
                  ))}
                </div>
              </div>
            )}
            {switched === null ? null : (
              <p className="note" role="status">
                {switched}
              </p>
            )}
            {failure === null ? null : <FailureNotice failure={failure} />}
            {asked === null ? null : (
              <ConfirmAction
                question={asked.kind === "switch" ? switchQuestion(asked.provider, asked.on) : checkQuestion(asked.provider)}
                consequence={
                  asked.kind === "switch" ? switchConsequence(asked.provider, asked.on) : checkConsequence(asked.provider)
                }
                confirmLabel={asked.kind === "switch" ? (asked.on ? SWITCH_ON : SWITCH_OFF) : SEND_THE_CHECK}
                cancelLabel={asked.kind === "switch" ? KEEP_IT_AS_IT_IS : DO_NOT_CHECK}
                busy={busy}
                onConfirm={() => {
                  send(asked);
                }}
                onCancel={() => {
                  setAsked(null);
                }}
              />
            )}
            {checked === null ? null : <CheckOutcome answer={checked} />}
            <ProvidersTable
              body={body}
              busy={busy}
              onAsk={(one) => {
                setFailure(null);
                setSwitched(null);
                setAsked(one);
              }}
            />
            <ProviderKeyForm
              body={body}
              onSaved={() => {
                void (async () => {
                  const again = await request<unknown>(PROVIDERS_API_PATH);
                  if (again.ok) {
                    setWritten(again.data);
                  }
                })();
              }}
            />
            <RungsTable body={body} />
            <ProviderRegister
              data={written !== null ? written : answer.data}
              onWritten={(plan) => {
                setFailure(null);
                setWritten(plan);
              }}
            />
            <RoutingSettings
              data={written !== null ? written : answer.data}
              onWritten={(plan) => {
                setFailure(null);
                setWritten(plan);
              }}
            />
          </>
        )}
      </Answered>
      {unmeasured === null ? null : <p className="note">{unmeasured}</p>}
    </section>
  );
}

function SpendByDepartment({ spend }: { readonly spend: Resource<unknown> }) {
  return (
    <section className="card" aria-labelledby="models-spend">
      <h2 id="models-spend">{SPEND_BY_DEPARTMENT}</h2>
      <Answered
        busy={spend.busy}
        failure={spend.failure}
        body={spend.data === null ? null : readSpendReport(spend.data)}
      >
        {(report) => {
          if (!report.built) {
            return <p className="note">{SPEND_NOT_BUILT}</p>;
          }
          const shares = spendShares(report);
          if (shares.length === 0) {
            return <p className="note">{NO_SPEND}</p>;
          }
          return (
            <>
              <dl className="fields">
                {shares.map((line) => (
                  <div className="fields__row" key={line.key}>
                    <dt>{line.key}</dt>
                    <dd>
                      <meter min={0} max={1} value={line.share} aria-label={`${line.key} share`} />{" "}
                      <span>{majorUnits(line.costMinor)}</span>
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="note">{SHARE_OF_THE_COST}</p>
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

/** The cards that need the models route's answer, and the four routes they borrow from. */
function ModelsAnswer({ models }: { readonly models: ModelsBody }) {
  const matrix = useResource<unknown>(chainApiPath());
  const latency = useResource<unknown>(answerLatencyApiPath(SERVICE_LEVELS_API_PATH));
  // Computed once per mount, so the address does not change under the effect that fetches it.
  const since = useMemo(() => spendSinceApiPath(SPEND_API_PATH, SPEND_DIMENSION, new Date()), []);
  const spend = useResource<unknown>(since);

  return (
    <>
      <Figures models={models} borrowed={{ matrix, latency, spend }} />
      <PriorityAndFallback models={models} matrix={matrix} />
      <ProviderHealth models={models} />
      <SpendByDepartment spend={spend} />
    </>
  );
}

export function Models() {
  const answer = useResource<unknown>(modelsApiPath());

  return (
    <article className="page">
      <h1>{MODELS_LABEL}</h1>
      <p className="lede">{MODELS_LEDE}</p>
      <p className="note">
        {WINDOW_LABEL}. <Link to={MATRIX_PATH}>{EDIT_ROUTING}</Link>
      </p>
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
