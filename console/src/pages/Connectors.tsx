/**
 * Connectors: every source this install connected, what each is trusted to read, connecting one,
 * and disconnecting one.
 *
 * `docs/screens.html` SCREEN 9 is the design of record and this is it as far as the data allows.
 * The table is the design's table in the design's column order, with who connected each source
 * and a disconnect control beside it. The cards under it are the design's two cards: one is the
 * copy policy, served whole by the API, and the other is connecting a source, which stands where
 * the design's "Add connector" action is.
 *
 * **What connecting starts, and what it still does not, is on the screen wherever connecting is
 * offered.** The worker reads a connected source on its own interval and nothing answers a question
 * from it yet. The API sends that sentence and this screen draws it above the form and in the
 * confirmation, so nobody presses Connect believing either more or less has started.
 *
 * **How reading each source went is the worker's record, drawn in its words.** The state and last
 * checked columns are the last attempt, the last read column is the last time the source was read
 * to the end, and the detail card carries the API's sentence about the attempt or about why nothing
 * reads the source. An attempt and a read are two columns because a source failing every hour is
 * attempted often and read never.
 *
 * **One thing the design asks for is still not drawn, and the screen says so rather than drawing it
 * from nothing.** There is no bar of today's calls against each ceiling, because nothing on the
 * server can count today's calls, and the column carries the API's reason.
 *
 * **Every write is confirmed in the API's words.** Connecting is `components/ConnectSource.tsx`,
 * which first run uses too; disconnecting opens `ConfirmAction` with the sentence the API served,
 * which says the key stays in the vault. A success says what changed and the list is read again.
 *
 * **An empty table and an absent one are drawn differently**, which is the point of the API
 * sending them differently. An empty table is a reader who may be told of no connected source. An
 * absent one is nothing on the server having looked, and it is drawn as a notice in the API's own
 * words, because an empty table here reads as a system that reads no outside data.
 *
 * A failure is the API's own sentence and the trace id. Including a 404, which here means the
 * caller may not read this screen: saying so would be the console explaining a refusal it did
 * not observe and cannot tell apart from an absence.
 *
 * Task ids: M42.6.5
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { ConnectSource } from "../components/ConnectSource";
import { Chip } from "../ui/Chip";
import { FailureNotice } from "../ui/FailureNotice";
import { Notice } from "../ui/Notice";
import { Status } from "../ui/Status";
import {
  CONNECTORS_API_PATH,
  CONNECTORS_LABEL,
  disconnectApiPath,
  keyWords,
  lastRead,
  offered,
  readConnectors,
  readTold,
  stateOf,
  TRUST_COLUMNS,
  TRUST_DETAIL,
  wasRead,
  when,
  type Connected,
  type Connectors as ConnectorsBody,
  type Trust,
} from "./connectorsQuery";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

/** The heading over the state where nothing on the server can say which sources are connected. */
export const NOTHING_LOOKED = "Nothing here can say which sources are connected";

/** The copy policy card's heading, in `docs/screens.html` SCREEN 9's own words. */
export const WHAT_WE_COPY = "What we copy, and what we never copy";

/** The heading over connecting a source. */
export const CONNECTING_A_SOURCE = "Connecting a source";

/** The heading over the sources this release cannot connect from here. */
export const CONNECTED_AT_THE_SERVER = "Connected at the server instead";

/**
 * What is said when the list came back and had nothing in it.
 *
 * A sentence rather than a blank, because a table with a caption and no rows reads as a table
 * that has not loaded. It mentions no rows, scopes or grants: a hint that there might be more
 * would tell the reader there are.
 */
export const NO_SOURCE_TO_SHOW = "There is no connected source this screen can show you.";

/** Said to a reader who holds no authority to connect any source. Their own grant, nobody else's. */
export const NOT_YOURS_TO_CONNECT =
  "Connecting a source needs the connector installation grant over that source, which you do not " +
  "hold, so there is no form here for you.";

/** Said to a reader whose grant covers only sources this screen cannot connect. */
export const NONE_OF_YOURS_FROM_HERE =
  "None of the sources your connector installation grant covers can be connected from this " +
  "screen. The reasons are below.";

/** The label of the select that chooses which source to connect. */
export const WHICH_SOURCE = "Source to connect";

export const DISCONNECT_LABEL = "Disconnect";
export const KEEP_CONNECTED = "Keep it connected";

/** One cell, with the two columns that are not plain text drawn as themselves. */
function cell(row: Trust, field: keyof Trust) {
  if (field === "health") {
    return <Status state={stateOf(row)} />;
  }
  if (field === "wiring") {
    return <Chip label={row.wiring} />;
  }
  if (field === "projected_fields") {
    // The design's own wording, "9 fields". A bare figure in a column beside rates and times
    // reads as a count of something else.
    return `${row.projected_fields} fields`;
  }
  const value = row[field];
  return value === null ? "" : String(value);
}

function Failure({ failure }: { readonly failure: ApiFailure }) {
  // `ui/FailureNotice.tsx`, so an unreachable API and a failing one are two headings here as on
  // every other screen.
  return (
    <section className="card">
      <FailureNotice failure={failure} />
    </section>
  );
}

function ConnectedTable({
  rows,
  budgetUnread,
  busy,
  onDisconnect,
}: {
  readonly rows: readonly Connected[];
  readonly budgetUnread: string;
  readonly busy: boolean;
  readonly onDisconnect: (row: Connected) => void;
}) {
  return (
    <>
      {/*
       * A plain table rather than `DataTable`, for `Limits.tsx`' reason: the table library is the
       * second heaviest thing in this console and `App.tsx` splits the routes that mount it.
       *
       * Wrapped in `.grid__scroll`, which is not decoration: `.grid__table` sets `overflow-wrap:
       * normal` so a column of identifiers is not split mid-word, and without a scrolling parent
       * the overflow is taken by the document, which takes the navigation off the side of a phone.
       */}
      <div className="grid__scroll">
        <table className="grid__table">
          <caption className="grid__caption">Every connected source this screen can show you</caption>
          <thead>
            <tr>
              {TRUST_COLUMNS.map((column) => (
                <th scope="col" key={column.field}>
                  {column.header}
                </th>
              ))}
              <th scope="col">Last read</th>
              <th scope="col">Connected</th>
              <th scope="col">Controls</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                {TRUST_COLUMNS.map((column) => (
                  <td key={column.field}>
                    {row.trust === null
                      ? column.field === "name"
                        ? row.name
                        : column.field === "credential"
                          ? keyWords(row)
                          : ""
                      : cell(row.trust, column.field)}
                  </td>
                ))}
                <td>{lastRead(row)}</td>
                <td>
                  <code>{row.connected_by}</code> {when(row.connected_at)}
                </td>
                <td>
                  {row.may_disconnect ? (
                    <button
                      type="button"
                      className="button"
                      aria-label={`${DISCONNECT_LABEL}: ${row.name}`}
                      disabled={busy}
                      onClick={() => {
                        onDisconnect(row);
                      }}
                    >
                      {DISCONNECT_LABEL}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">{budgetUnread}</p>
    </>
  );
}

function ConnectedDetail({ row }: { readonly row: Connected }) {
  return (
    <section className="card">
      <h2>{row.name}</h2>
      <p className={row.pinned ? "note" : undefined}>{row.declaration}</p>
      <dl className="fields" aria-label={`What ${row.name} is trusted to read`}>
        {row.trust === null
          ? null
          : TRUST_DETAIL.map((one) => (
              <div className="fields__row" key={one.field}>
                <dt>{one.label}</dt>
                <dd>
                  <span>{String(row.trust?.[one.field])}</span>
                </dd>
              </div>
            ))}
        <div className="fields__row">
          <dt>Key</dt>
          <dd>
            <span>{keyWords(row)}</span>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Reading</dt>
          <dd>
            <span>{row.sync}</span>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Last read</dt>
          <dd>
            <span>{lastRead(row)}</span>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function ConnectCard({
  page,
  onConnected,
}: {
  readonly page: ConnectorsBody;
  readonly onConnected: (told: string) => void;
}) {
  const sources = offered(page.connectable);
  // The first source this reader may connect is chosen to begin with, so the form is on the page
  // and a person with one source to connect is not asked to choose it first.
  const [chosen, setChosen] = useState(sources[0]?.name ?? "");
  const source = sources.find((one) => one.name === chosen);
  return (
    <section className="card">
      <h2>{CONNECTING_A_SOURCE}</h2>
      {/*
       * The API's sentence, shown to everybody who may open this screen and not only to whoever
       * may connect: somebody who cannot do it still has to know what it would and would not do.
       */}
      <p>{page.connecting}</p>
      {page.vault_told === "" ? null : <p className="note">{page.vault_told}</p>}
      {sources.length === 0 ? (
        <p className="note">{page.may_connect ? NONE_OF_YOURS_FROM_HERE : NOT_YOURS_TO_CONNECT}</p>
      ) : (
        <>
          <label className="control-label" htmlFor="connect-which">
            {WHICH_SOURCE}
          </label>
          <select
            id="connect-which"
            className="form-control"
            value={chosen}
            onChange={(event) => {
              setChosen(event.target.value);
            }}
          >
            {sources.map((one) => (
              <option key={one.name} value={one.name}>
                {one.label}
              </option>
            ))}
          </select>
          {source === undefined ? null : (
            <ConnectSource
              key={source.name}
              source={source}
              confirmation={page.confirm_connect}
              keyMaxChars={page.key_max_chars}
              keyBlank={page.key_blank}
              onConnected={onConnected}
            />
          )}
        </>
      )}
      {page.not_connectable.length === 0 ? null : (
        <>
          <h3>{CONNECTED_AT_THE_SERVER}</h3>
          <dl className="fields" aria-label={CONNECTED_AT_THE_SERVER}>
            {page.not_connectable.map((one) => (
              <div className="fields__row" key={one.name}>
                <dt>{one.label}</dt>
                <dd>
                  <span>{one.why}</span>
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </section>
  );
}

function ConnectorsPage({
  page,
  onChanged,
}: {
  readonly page: ConnectorsBody;
  readonly onChanged: (sentence: string) => void;
}) {
  const list = readConnectors(page);
  const [leaving, setLeaving] = useState<Connected | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const disconnect = useCallback(
    (row: Connected) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(disconnectApiPath(row.name), { method: "POST" });
        setBusy(false);
        setLeaving(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onChanged(readTold(result.data));
      })();
    },
    [onChanged],
  );

  return (
    <>
      {failure === null ? null : <Failure failure={failure} />}

      {!wasRead(list) ? (
        <section className="card">
          <Notice title={NOTHING_LOOKED}>
            <p>{list.unread}</p>
          </Notice>
        </section>
      ) : (
        <section className="card">
          <h2>Connected sources</h2>
          {list.rows.length === 0 ? (
            <p className="note">{NO_SOURCE_TO_SHOW}</p>
          ) : (
            <ConnectedTable
              rows={list.rows}
              budgetUnread={page.budget_unread}
              busy={busy}
              onDisconnect={(row) => {
                setFailure(null);
                setLeaving(row);
              }}
            />
          )}
          {leaving === null ? null : (
            <ConfirmAction
              question={`${DISCONNECT_LABEL} ${leaving.name}?`}
              consequence={page.confirm_disconnect}
              confirmLabel={DISCONNECT_LABEL}
              cancelLabel={KEEP_CONNECTED}
              busy={busy}
              onConfirm={() => {
                disconnect(leaving);
              }}
              onCancel={() => {
                setLeaving(null);
              }}
            />
          )}
        </section>
      )}

      {/*
       * What each source is trusted to read, as sentences under its own heading rather than as
       * more columns. They are paragraphs and a table of paragraphs is unreadable at any width;
       * they are also the part of this screen somebody reads once, carefully, before deciding
       * whether a source is safe to leave connected.
       */}
      {wasRead(list) ? list.rows.map((row) => <ConnectedDetail key={`trust-${row.name}`} row={row} />) : null}

      <ConnectCard page={page} onConnected={onChanged} />

      {page.copy_policy.length > 0 ? (
        <section className="card">
          <h2>{WHAT_WE_COPY}</h2>
          <dl className="fields" aria-label={WHAT_WE_COPY}>
            {page.copy_policy.map((line) => (
              <div className="fields__row" key={line.what}>
                <dt>{line.what}</dt>
                <dd>
                  <Chip label={line.verdict} />
                  <p className="note">{line.why}</p>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}
    </>
  );
}

function ConnectorList({ onChanged }: { readonly onChanged: (sentence: string) => void }) {
  const answer = useResource<ConnectorsBody>(CONNECTORS_API_PATH);
  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy || answer.data === null) {
    return (
      <p className="note" role="status">
        Reading which sources this install has connected.
      </p>
    );
  }
  return <ConnectorsPage page={answer.data} onChanged={onChanged} />;
}

export function Connectors() {
  // A counter rather than a boolean, so two changes in a row read the list twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [changed, setChanged] = useState<string | null>(null);
  const onChanged = useCallback((sentence: string) => {
    setChanged(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <h1>{CONNECTORS_LABEL}</h1>
      <p className="lede">
        Every outside system this install connected, what each one was connected to, what it is
        allowed to do there, and connecting another.
      </p>
      {changed === null ? null : (
        <p className="note" role="status">
          {changed}
        </p>
      )}
      <ConnectorList key={generation} onChanged={onChanged} />
    </article>
  );
}
