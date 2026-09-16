/**
 * File and object storage: the buckets this product keeps, how long each keeps what it holds and
 * why, where the store is, and what cannot be known from here.
 *
 * `docs/screens.html` does not draw storage. The owner's standard lists it, so the screen takes the
 * design's general shape and says in the API's words what is missing: nothing in the application
 * connects to the store yet, usage is not measured, object names are never listed, and a retention
 * changes in a release rather than from a browser. There is no control on this screen, and each of
 * those sentences is why.
 *
 * Task ids: M27.8.15
 */

import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import { STORAGE_API_PATH, keptFor, readStorage } from "./storageQuery";

export const STORAGE_HEADING = "File and object storage";
export const STORAGE_CRUMB = "Install › Storage";
export const STORAGE_LEDE =
  "The buckets this install keeps files in, how long each keeps them and why, and where the " +
  "store is. Files are never listed by name.";

export const READING_STORAGE = "Reading how files are kept.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NOT_A_READABLE_ADDRESS = "The address set for the store is not one this screen can show.";
export const FROM_DEFAULT = "This is the address a new install starts with; nobody has set another.";

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

function StorageBody() {
  const answer = useResource<unknown>(STORAGE_API_PATH);
  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_STORAGE}
      </p>
    );
  }
  const page = readStorage(answer.data);
  if (page === null) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK}>
        <p>The answer about storage was not in a shape this screen can read.</p>
      </Notice>
    );
  }
  return (
    <>
      <section className="card">
        <h2>Where the store is</h2>
        <dl className="fields">
          <div className="fields__row">
            <dt>Address</dt>
            <dd>
              {page.endpoint.address === null ? NOT_A_READABLE_ADDRESS : <code>{page.endpoint.address}</code>}
            </dd>
          </div>
          <div className="fields__row">
            <dt>Prefix</dt>
            <dd>
              <code>{page.endpoint.prefix}</code>
            </dd>
          </div>
        </dl>
        {page.endpoint.from_default ? <p className="note">{FROM_DEFAULT}</p> : null}
        <p className="note">{page.endpoint.told}</p>
        <p className="note">{page.connection}</p>
      </section>

      <section className="card">
        <h2>Buckets</h2>
        <div className="grid__scroll">
          <table className="grid__table" aria-label="Buckets">
            <thead>
              <tr>
                <th scope="col">Bucket</th>
                <th scope="col">Holds</th>
                <th scope="col">Kept for</th>
                <th scope="col">Why</th>
                <th scope="col">Versioned</th>
                <th scope="col">Readable without signing in</th>
              </tr>
            </thead>
            <tbody>
              {page.buckets.map((bucket) => (
                <tr key={bucket.name}>
                  <td>
                    <code>{bucket.name}</code>
                  </td>
                  <td>
                    {bucket.holds}
                    {bucket.kinds.length === 0 ? null : <> ({bucket.kinds.join(", ")})</>}
                  </td>
                  <td>{keptFor(bucket)}</td>
                  <td>{bucket.retention_reason}</td>
                  <td>{bucket.versioned ? "Yes" : "No"}</td>
                  <td>{bucket.public_read ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {page.findings.length === 0 ? null : (
          <ul aria-label="Findings about the buckets">
            {page.findings.map((one) => (
              <li key={one}>{one}</li>
            ))}
          </ul>
        )}
        <p className="note">{page.retention}</p>
      </section>

      <section className="card">
        <h2>What is not shown</h2>
        <p>{page.usage}</p>
        <p>{page.names}</p>
      </section>
    </>
  );
}

export function Storage() {
  return (
    <article className="page">
      <p className="note">{STORAGE_CRUMB}</p>
      <h1>{STORAGE_HEADING}</h1>
      <p className="lede">{STORAGE_LEDE}</p>
      <StorageBody />
    </article>
  );
}
