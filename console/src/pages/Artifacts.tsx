/**
 * Artifacts: what the system produced, for whom, when, what made it, and how long it is kept.
 *
 * `docs/screens.html` draws artifacts in one place, the "Artifacts it produced" card inside
 * SCREEN 13, with an Artifact, a For and a When column and a hint about the entitlement an
 * artifact carries. This is that card across every agent this reader may see, under Govern where
 * `brain.console.screens` registers it, with the design's three columns first and the two the
 * leaf adds after them: how it was made and how long it is kept.
 *
 * **On every install today there is no list, and the page says why in the API's words.**
 * `brain.artifact_routes` answers a sentence while nothing records an artifact, and this page
 * draws the sentence under its own heading rather than an empty table, because an empty table
 * under this heading reads as an estate that produced nothing.
 *
 * **What the design's hint becomes.** SCREEN 13 says re-downloading re-checks the requester. No
 * download is served here, because the files are held nowhere this system reads, so the hint
 * keeps the half that is true and says what is not offered.
 *
 * **Nothing here decides who may see anything.** The request is identical for every caller, and a
 * 404 is the API saying this caller may not open the screen.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet.
 *
 * Task ids: none
 */

import { useState } from "react";
import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import {
  ARTIFACTS_API_PATH,
  NO_ARTIFACT_FILTERS,
  ORDERS,
  ORDER_LABELS,
  keptUntil,
  narrowed,
  offeredKinds,
  readArtifacts,
  wasRead,
  when,
  type ArtifactFilters,
  type ArtifactRow,
  type ArtifactsView,
  type Order,
} from "./artifactsQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const ARTIFACTS_HEADING = "Artifacts";
export const ARTIFACTS_CRUMB = "Govern › Artifacts";
export const ARTIFACTS_LEDE =
  "What the system produced: documents, decks, reports, exports and images, with who each was " +
  "made for, what made it, and when it stops being kept.";

/** The four states. */
export const READING_ARTIFACTS = "Reading what was produced.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NOTHING_RECORDED = "Nothing on this install records what was produced";
export const NO_ARTIFACTS = "There are no artifacts to show.";
export const NONE_MATCH = "No artifact on this page matches.";

/** What the controls act on, said beside them. */
export const NARROWS_THIS_PAGE = "Search, filter and order work on the artifacts this page holds.";

/** SCREEN 13's hint, with the half that is not offered said plainly. */
export const CARRIES_ITS_RUN =
  "An artifact carries the entitlement of the run that made it, so a report built for one person " +
  "cannot be forwarded into wider visibility than its contents allow. There is no download on " +
  "this page: the files are not held anywhere this system reads, and a download would check the " +
  "person asking at that moment rather than trust a link.";

export const ARTIFACTS_CAPTION = "Artifacts this page holds";
export const FILTERS_LABEL = "Narrow the artifacts";
export const EVERY_KIND = "Every kind";
export const KEPT_RULE_HEADING = "How long an artifact is kept";

function Rows({ rows }: { readonly rows: readonly ArtifactRow[] }) {
  const [filters, setFilters] = useState<ArtifactFilters>(NO_ARTIFACT_FILTERS);
  const shown = narrowed(rows, filters);

  if (rows.length === 0) {
    return <p className="note">{NO_ARTIFACTS}</p>;
  }
  return (
    <>
      <form className="form" aria-label={FILTERS_LABEL} onSubmit={(event) => event.preventDefault()}>
        <label className="control-label">
          Search{" "}
          <input
            className="form-control"
            type="search"
            value={filters.search}
            onChange={(event) => {
              setFilters({ ...filters, search: event.target.value });
            }}
          />
        </label>
        <label className="control-label">
          Kind{" "}
          <select
            className="form-control"
            value={filters.kind}
            onChange={(event) => {
              setFilters({ ...filters, kind: event.target.value });
            }}
          >
            <option value="">{EVERY_KIND}</option>
            {offeredKinds(rows).map((one) => (
              <option key={one} value={one}>
                {one}
              </option>
            ))}
          </select>
        </label>
        <label className="control-label">
          Order{" "}
          <select
            className="form-control"
            value={filters.order}
            onChange={(event) => {
              setFilters({ ...filters, order: event.target.value as Order });
            }}
          >
            {ORDERS.map((one) => (
              <option key={one} value={one}>
                {ORDER_LABELS[one]}
              </option>
            ))}
          </select>
        </label>
        <p className="note">{NARROWS_THIS_PAGE}</p>
      </form>
      {shown.length === 0 ? (
        <p className="note">{NONE_MATCH}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={ARTIFACTS_CAPTION}>
            <thead>
              <tr>
                <th scope="col">Artifact</th>
                <th scope="col">For</th>
                <th scope="col">When</th>
                <th scope="col">Made by</th>
                <th scope="col">Kept until</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr key={row.artifact_id}>
                  <td>
                    <code>{row.artifact_id}</code> {row.kind}
                    {row.state === "current" ? null : (
                      <span className="note">
                        {" "}
                        {row.state}
                        {row.superseded_by === "" ? "" : ` by ${row.superseded_by}`}
                      </span>
                    )}
                  </td>
                  <td>
                    <code>{row.produced_for}</code>
                  </td>
                  <td>{when(row.produced_at)}</td>
                  <td>
                    <code>{row.agent_id}</code> version <code>{row.agent_version}</code>, run{" "}
                    <code>{row.run_id}</code>
                  </td>
                  <td>
                    {keptUntil(row)} <span className="note">({row.kept_as})</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function Artifacts() {
  const answer = useResource<ArtifactsView>(ARTIFACTS_API_PATH);
  const read = readArtifacts(answer.data);

  return (
    <article className="page">
      <p className="note">{ARTIFACTS_CRUMB}</p>
      <h1>{ARTIFACTS_HEADING}</h1>
      <p className="lede">{ARTIFACTS_LEDE}</p>

      {answer.failure ? (
        <section className="card">
          <Notice
            title={
              answer.failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK
            }
            traceId={answer.failure.traceId}
          >
            <p>{answer.failure.message}</p>
          </Notice>
        </section>
      ) : null}

      {answer.busy ? (
        <p className="note" role="status">
          {READING_ARTIFACTS}
        </p>
      ) : null}

      {answer.data === null ? null : (
        <>
          <section className="card">
            <h2>Artifacts produced</h2>
            {wasRead(read) ? (
              <Rows rows={read.panel} />
            ) : (
              <>
                <p>
                  <strong>{NOTHING_RECORDED}</strong>
                </p>
                <p>{read.unread}</p>
              </>
            )}
            <p className="note">{CARRIES_ITS_RUN}</p>
          </section>
          <section className="card">
            <h2>{KEPT_RULE_HEADING}</h2>
            <p>{answer.data.kept_rule}</p>
          </section>
        </>
      )}
    </article>
  );
}
