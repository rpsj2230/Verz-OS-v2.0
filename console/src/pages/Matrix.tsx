/**
 * The routing matrix, and the editor for one rung of it.
 *
 * `brain.models.routing.RoutingChain` says why this screen exists: "In Postgres this is
 * `routing_rung`, editable from the console at runtime. Tier assignment changes roughly
 * monthly as providers ship models, and a change that needs an engineer and a release is a
 * change that stops happening, after which the pools rot." Until this screen the table was
 * reachable by nothing, so every timeout was still a deploy.
 *
 * **The address is the whole of the state.** `/routing` is the matrix and
 * `/routing/{rungId}` is the matrix with one rung's editor open, so a person can send a
 * colleague the rung they are arguing about. Holding the open rung in component state
 * instead would make the editor unlinkable and would put the back button somewhere it does
 * not belong.
 *
 * **Nothing here decides what may be seen or changed.** The request goes out identically for
 * every caller; the API answers from grants this browser never receives; a refusal comes
 * back as a value and is rendered in the API's own words. `editable` on the response decides
 * whether an edit control is drawn and decides nothing else, and every save is refused or
 * accepted by the route whatever this file believed. See `A_HIDDEN_EDITOR_IS_NOT_A_REFUSAL`.
 *
 * **The screen says nothing about how many rungs there are.** Not a total, not a page
 * number, not the count of what arrived. The grid holds that rule for the table; this file
 * holds it for everything around the table, which is where a heading like "4 rungs" would
 * go. What it does say, when the page came back full, is that there is more, in a sentence
 * with no number in it: that is `truncated`, and it is a flag rather than an arithmetic.
 *
 * **A saved edit is followed by a fresh request rather than by a local update.** The rows
 * component is keyed on a counter this file bumps, so a successful save remounts it and it
 * asks again. Patching the row in place would show what the console sent, and the whole
 * reason `brain.routing_routes.apply_edit` returns the stored row is that the value written
 * and the value stored are about to stop being the same thing: M5.3.2 derives `role` on
 * write, so a console trusting its own request would report a label the database does not
 * hold.
 *
 * **The form is a form rather than four boxes, and the argument is the bounds in it.**
 * `PATCH /api/v1/routing/rungs/{rung_id}` bounds all four fields, and a hand-written control
 * would be a third copy of those numbers after the route and its document. The copy nobody
 * keeps in step is the one that offers a person a number the API refuses, which returns
 * `HTTPValidationError` rather than `ErrorBody` and therefore reads as "Something went
 * wrong." The schema is in `matrixQuery.ts` and its numbers are checked against the route's
 * own description.
 *
 * **The form library is the records screen's, so this route is code-split too.**
 * `@rjsf/core` with the ajv validator is the largest thing in this console by a wide margin,
 * and a second eager import of it would put it back in the entry chunk for everybody
 * including a person who only opens the overview. `App.tsx` loads this route on demand and
 * `tests/bundle-split.test.ts` walks the static import graph to prove it.
 *
 * **A save goes through the matrix gate, and a held save says so with its failing cases.** Since
 * M5.6.2 the PATCH answers the change as `ops.routing_change` recorded it: applied, or held because
 * a golden question or a permission canary regressed on the changed ladder. A held change is drawn
 * above the matrix with the cases that held it, from `components/MatrixGate.tsx`, and the rung keeps its numbers.
 *
 * Task ids: M5.3.3, M27.8.4, M5.6.2
 */

import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { DataTable } from "../components/DataTable";
import { SchemaForm } from "../components/SchemaForm";
import {
  editableDefaults,
  MATRIX_API_PATH,
  MATRIX_FILTERS,
  openRungApiPath,
  matrixColumns,
  readMatrixPage,
  RUNG_EDIT_SCHEMA,
  RUNG_EDIT_UI,
  rungAddress,
  rungApiPath,
  rungById,
  submittedEdit,
  type RungEdit,
  type RungRow,
} from "./matrixQuery";
import { ConfirmAction } from "../components/ConfirmAction";
import { ChangeDecided, MatrixGate } from "../components/MatrixGate";
import { readChange, type ChangeRow } from "./matrixGateQuery";

/**
 * What is said when the page came back full.
 *
 * No number, and none available to put in one: `readMatrixPage` keeps a flag. It says the route's
 * load came back full, which "Show more" cannot reach past, so the sentence says what is true
 * rather than offering an action that does not exist.
 */
const THERE_IS_MORE = "This page came back full, so there are more rungs than it shows.";

/**
 * What is said when the address names a rung the page does not carry.
 *
 * About this page and not about the matrix, which is what makes it safe to say at all.
 * Every reader of the matrix is answered every live rung, so a rung absent from the grid is
 * absent from the live matrix and the reader can see the grid; there is no hidden set for
 * this sentence to describe. The same sentence on a records screen would be a disclosure,
 * which is why it is written here rather than in a shared component.
 */
const NO_SUCH_RUNG = "No rung on this page has that id.";

/** The confirmation's two buttons. */
export const SAVE_RUNG = "Save these numbers";
export const KEEP_RUNG = "Keep the rung as it is";

/** The question a save asks, naming the rung by its place in the matrix and what it runs. */
export function saveRungQuestion(rung: RungRow): string {
  return `Save new numbers to the ${rung.tier} tier's rung at position ${String(rung.position)} (${rung.provider} ${rung.model})?`;
}

/**
 * What a save does, in words that are true on every install today.
 *
 * **It is judged before it takes traffic.** `brain.models.calls` reads the ladder on every call, so
 * an applied edit is the chain the next question walks; since M5.6.2 the edit is first run against
 * the golden questions and the permission canaries, and a regression holds it with the failing
 * cases shown. A confirmation promising the new numbers unconditionally would be a person agreeing
 * to something the system may refuse, which is the one thing a confirmation may not be.
 */
export function saveRungConsequence(edit: RungEdit): string {
  return (
    `The rung would hold ${String(edit.attempts)} attempt${edit.attempts === 1 ? "" : "s"}, ` +
    `a ${String(edit.timeout_seconds)} second timeout and at most ${String(edit.max_concurrency)} at once, ` +
    `and be switched ${edit.enabled ? "on" : "off"}. The change is run against the golden questions ` +
    "and the permission canaries first: if nothing regresses the next question walks it, and if " +
    "something does it is held with the failing cases shown and the rung keeps its numbers."
  );
}

/**
 * One rung's editor.
 *
 * A separate component because it holds the state of one save in flight and the matrix does
 * not. Merging the two would put a busy flag belonging to a PATCH on a component whose other
 * job is rendering a GET, and the first person to reuse it would find the grid greyed out
 * while somebody typed.
 */
function RungEditor({
  rung,
  onSaved,
}: {
  readonly rung: RungRow;
  readonly onSaved: (decided: ChangeRow | null) => void;
}) {
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  // The edit waiting on its confirmation. A save overwrites what the rung holds, so the form's
  // submit asks first and only the confirmation sends: `tests/destructive-confirmed.test.ts`.
  const [pending, setPending] = useState<RungEdit | null>(null);

  const ask = useCallback((submitted: unknown) => {
    const edit = submittedEdit(submitted);
    if (edit === null) {
      // Not an edit this screen recognises. Doing nothing is the answer: a PATCH built out
      // of values nobody read is a write nobody meant to make, and this is the one screen
      // here where a wrong request changes something.
      return;
    }
    setFailure(null);
    setPending(edit);
  }, []);

  const save = useCallback(
    (edit: RungEdit) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(rungApiPath(rung.id), {
          method: "PATCH",
          body: edit,
        });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        // The change as the gate decided it goes up to the page, which draws a held one with its
        // cases, and the matrix is asked again. The stored row is not drawn from the answer: the
        // row in the grid and the row in the form would be two copies of one thing that can
        // disagree, and the one a reader trusts would be whichever was on the screen.
        onSaved(readChange(result.data));
      })();
    },
    [rung.id, onSaved],
  );

  return (
    <section className="card">
      <SchemaForm
        caption={`Rung ${rung.tier} position ${String(rung.position)}`}
        schema={RUNG_EDIT_SCHEMA}
        uiSchema={RUNG_EDIT_UI}
        formData={editableDefaults(rung)}
        failure={failure}
        busy={busy || pending !== null}
        onSubmit={ask}
      />
      {pending === null ? null : (
        <ConfirmAction
          question={saveRungQuestion(rung)}
          consequence={saveRungConsequence(pending)}
          confirmLabel={SAVE_RUNG}
          cancelLabel={KEEP_RUNG}
          busy={busy}
          onConfirm={() => {
            save(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}
    </section>
  );
}

/** What the controls narrow, and what a narrowed matrix with no rung says. */
export const FILTERS_LABEL = "Narrow the matrix";
export const NONE_MATCH = NOTHING_MATCHES;

/**
 * The matrix itself, and the rung that is open.
 *
 * The rows are `useListing`'s, so the search, the filters and "Show more" are requests, and the
 * order is the chain's, which is the only order the route takes. The open rung is a request of its
 * own, filtered to the id in the address, so its editor opens whichever page it sits on. A save
 * moves `version` and both are asked again.
 */
function MatrixRows({
  openRungId,
  version,
  onSaved,
}: {
  readonly openRungId: string | undefined;
  readonly version: number;
  readonly onSaved: (decided: ChangeRow | null) => void;
}) {
  const listing = useListing<RungRow>(MATRIX_API_PATH, { choices: MATRIX_FILTERS, version });
  const opened = useResource<unknown>(openRungId === undefined ? null : openRungApiPath(openRungId), version);
  const page = useMemo(() => readMatrixPage(listing.body), [listing.body]);
  const openPage = useMemo(() => readMatrixPage(opened.data), [opened.data]);

  const columns = useMemo(
    () =>
      matrixColumns(page.editable, (rungId) => (
        <Link to={rungAddress(rungId)}>Edit</Link>
      )),
    [page.editable],
  );

  const open = openRungId === undefined ? null : rungById(openPage.rungs, openRungId);

  return (
    <>
      <ListControls label={FILTERS_LABEL} listing={listing} choices={MATRIX_FILTERS} />
      <DataTable
        caption="The routing matrix"
        columns={columns}
        rows={page.rungs}
        rowId={(rung) => rung.id}
        failure={listing.failure}
        busy={listing.busy}
      />
      {!listing.busy && listing.failure === null && page.rungs.length === 0 && narrows(listing.question) ? (
        <p className="note">{NONE_MATCH}</p>
      ) : null}
      <ShowMore listing={listing} />

      {page.truncated ? <p className="note">{THERE_IS_MORE}</p> : null}

      {/*
       * The editor appears when a rung is open and this caller may change it. When they may
       * not, nothing is rendered and nothing is said: a sentence explaining that they cannot
       * edit would be this console describing a refusal the API never made, and the API's
       * refusal, when a save is attempted, is the same one it gives somebody who cannot read
       * the matrix at all.
       */}
      {open !== null && openPage.editable ? <RungEditor rung={open} onSaved={onSaved} /> : null}

      {openRungId !== undefined && open === null && !opened.busy && opened.failure === null ? (
        <p className="note">{NO_SUCH_RUNG}</p>
      ) : null}

      {/*
       * The gate's changes and golden questions are asked for whatever the editable flag says and
       * whichever rung is open, so neither decides what is asked: a reader the API refuses is shown
       * its refusal. Its forms are drawn for an editor on the matrix itself, and not while one
       * rung's editor is open, so the open rung's form is the only form beside it.
       */}
      <MatrixGate
        version={version}
        editable={page.editable && openRungId === undefined}
        onChanged={() => {
          onSaved(null);
        }}
      />
    </>
  );
}

export function Matrix() {
  const { rungId } = useParams();
  // A counter rather than a boolean, because two saves in a row must remount twice. Its
  // value is never rendered: it is a key, and a key that reached the screen would be a
  // number describing how many times somebody had saved.
  const [version, setVersion] = useState(0);
  // The last change a save on this page decided, drawn above the matrix when the gate held it.
  const [decided, setDecided] = useState<ChangeRow | null>(null);
  const onSaved = useCallback((change: ChangeRow | null) => {
    if (change !== null) {
      setDecided(change);
    }
    setVersion((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <h1>Routing matrix</h1>
      <p className="lede">
        Which model handles a request, in what order, and what each rung is allowed to spend.
      </p>

      {decided === null || decided.status !== "held" ? null : (
        <section className="card" role="status" aria-label="The change was held">
          <ChangeDecided change={decided} />
        </section>
      )}

      <MatrixRows openRungId={rungId} version={version} onSaved={onSaved} />
    </article>
  );
}

/**
 * The two sentences this page adds to what the API said, exported so a test can assert on
 * them rather than on a copy. Neither carries a number and neither explains a refusal.
 */
export { THERE_IS_MORE, NO_SUCH_RUNG };
