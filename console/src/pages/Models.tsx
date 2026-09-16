/**
 * Models and health: which model answers each tier, in what order the chain falls back, the
 * providers behind it, and what the install cannot yet measure about any of them.
 *
 * `docs/screens.html` SCREEN 11 is the design of record and this page is its layout: the bar with
 * the window and Edit routing, four figures, the Priority and fallback table, and Provider health
 * beside Spend by department. `modelsQuery.ts` holds the arguments; the facts are in
 * `brain.operate_routes`, `brain.routing_routes`, `brain.report_routes` and
 * `brain.console.operate`, which decides whether this screen's own figures open at all.
 *
 * **Where the design draws something with no source, the page draws the thing that is true and
 * says what is missing.** No model is called by this install, so Fallbacks fired is a sentence
 * rather than a number, Provider health lists the providers and says their health is not
 * recorded rather than drawing bars, and the table's Budget and p95 columns are absent with one
 * sentence saying why. Whether a provider's key is held is not served by any route this page
 * reads, and the card says it arrives with the vault work rather than guessing.
 *
 * **Edit routing is a link, and it is the design's.** The chain's four operational numbers are
 * edited on the routing screen, behind the matrix's write grant, where the form checks them
 * against the route's own bounds. A second editor here would be a second copy of those bounds and
 * a second place a rung could be taken out of rotation without the first screen knowing.
 *
 * **Each card is loaded, failed or answered on its own.** A reader may hold the models screen and
 * not the usage grant, and the spend card then carries the API's refusal while the chain is
 * drawn; a single spinner or a single failure for the page would hide three answers behind the
 * one that did not come back. Loading, unreachable, refused and unreadable are different
 * sentences in every card.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet of its
 * own. `matrixQuery.ts` is imported for its path and its reader, and its only imports of the form
 * library are types, which a build erases.
 *
 * Task ids: M27.2.3
 */

import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ApiFailure } from "../api/errors";
import { useResource, type Resource } from "../api/useResource";
import { Chip } from "../ui/Chip";
import { Notice } from "../ui/Notice";
import { matrixApiPath, MATRIX_PATH, readMatrixPage, type RungRow } from "./matrixQuery";
import {
  answerLatencyApiPath,
  answerReading,
  chainRows,
  HEALTH_NOT_RECORDED,
  KEY_STATUS_ARRIVES_WITH_THE_VAULT,
  measureSentence,
  MODELS_LABEL,
  modelsApiPath,
  NO_KEY_SLOT,
  NO_MODEL_TIER,
  providerRows,
  readModels,
  spendShares,
  spendSinceApiPath,
  WINDOW_DAYS,
  withoutAModel,
  type ModelsBody,
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
  "Which model answers each tier and what the chain falls back to, the providers behind it, and " +
  "what this install measures about them.";

/** The window, in the design's words. */
export const WINDOW_LABEL = `Last ${String(WINDOW_DAYS)} days`;

/** The four figures' labels, in the design's words. */
export const WITHOUT_A_MODEL = "Answered without a model";
export const P95_ANSWER = "p95 answer";
export const FALLBACKS_FIRED = "Fallbacks fired";
export const COST = `Cost ${String(WINDOW_DAYS)}d`;

export const PRIORITY_AND_FALLBACK = "Priority and fallback";
export const PROVIDER_HEALTH = "Provider health";
export const SPEND_BY_DEPARTMENT = "Spend by department";
export const EDIT_ROUTING = "Edit routing";

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
    return (
      <Notice
        title={failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK}
        traceId={failure.traceId}
      >
        <p>{failure.message}</p>
      </Notice>
    );
  }
  if (body === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }
  return <>{children(body)}</>;
}

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
  const fallbacks = models.unmeasured.find((one) => one.measure === "fallback_count");
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
            <span>{NOT_MEASURED}</span>
            {fallbacks === undefined ? null : (
              <p className="note">{measureSentence(fallbacks.measure, fallbacks.because)}</p>
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
  const noModel = models.unmeasured.find((one) => one.measure === "model");

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
      {noModel === undefined ? null : (
        <p className="note">{measureSentence(noModel.measure, noModel.because)}</p>
      )}
    </section>
  );
}

function ProviderHealth({
  models,
  matrix,
}: {
  readonly models: ModelsBody;
  readonly matrix: Resource<unknown>;
}) {
  const unmeasured = models.unmeasured.find((one) => one.measure === "provider");
  // The chain's rungs when the matrix answered, and none when it did not: the providers are the
  // models route's and are listed whatever the matrix said, and "In the chain" is then empty
  // rather than the card waiting on a request that belongs to the card above.
  const rows = providerRows(models.providers, readMatrixPage(matrix.data).rungs);

  return (
    <section className="card" aria-labelledby="models-providers">
      <h2 id="models-providers">{PROVIDER_HEALTH}</h2>
      <div className="grid__scroll">
        <table className="grid__table">
          <caption className="grid__caption">
            Every provider this system can hold a key for, and where the chain names it
          </caption>
          <thead>
            <tr>
              <th scope="col">Provider</th>
              <th scope="col">What it is for</th>
              <th scope="col">In the chain</th>
              <th scope="col">Health</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.provider}>
                <td>
                  <code>{row.provider}</code>
                </td>
                <td>{row.description ?? NO_KEY_SLOT}</td>
                <td>{row.inChain.length === 0 ? "-" : row.inChain.join(", ")}</td>
                <td>{models.breaker_state_is_not_recorded ? HEALTH_NOT_RECORDED : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {unmeasured === undefined ? null : (
        <p className="note">{measureSentence(unmeasured.measure, unmeasured.because)}</p>
      )}
      {models.key_status_is_not_served ? (
        <p className="note">{KEY_STATUS_ARRIVES_WITH_THE_VAULT}</p>
      ) : null}
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

/** The cards that need the models route's answer, and the three routes they borrow from. */
function ModelsAnswer({ models }: { readonly models: ModelsBody }) {
  const matrix = useResource<unknown>(matrixApiPath());
  const latency = useResource<unknown>(answerLatencyApiPath(SERVICE_LEVELS_API_PATH));
  // Computed once per mount, so the address does not change under the effect that fetches it.
  const since = useMemo(() => spendSinceApiPath(SPEND_API_PATH, SPEND_DIMENSION, new Date()), []);
  const spend = useResource<unknown>(since);

  return (
    <>
      <Figures models={models} borrowed={{ matrix, latency, spend }} />
      <PriorityAndFallback models={models} matrix={matrix} />
      <ProviderHealth models={models} matrix={matrix} />
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
