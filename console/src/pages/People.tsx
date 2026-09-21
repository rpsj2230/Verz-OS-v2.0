/**
 * People and grants: who holds what, and the two controls that change it.
 *
 * **The address is the whole of the state.** `/people` is the listing and `/people/{subject}`
 * is the listing with one subject open, so a person can send a colleague the row they are
 * arguing about. Holding the open subject in component state would make it unlinkable and
 * would put the back button somewhere it does not belong. That is `Matrix.tsx`'s arrangement
 * and its reason.
 *
 * **The deep link is resolved against the page and never against a route of its own.** There is
 * no `GET /govern/people/{subject}`, and `brain.govern_routes.
 * A_DEEP_LINK_RESOLVED_AGAINST_THE_PAGE_CANNOT_BE_AN_ORACLE` says why: a route answering one
 * subject by key would answer, for anybody able to type one, whether that subject holds a grant
 * the reader may not see, unless its two refusals were identical in every particular. Resolving
 * against rows the reader was already shown cannot be an oracle, and the sentence this page
 * says when the key matches nothing is about this page rather than about the estate.
 *
 * **An empty capability list means two things and this page says neither.** See
 * `governQuery.AN_EMPTY_CAPABILITY_LIST_MEANS_TWO_THINGS_AND_SAYS_NEITHER`. There is no lock
 * icon, no dash with a tooltip and no sentence under the table, because every one of those
 * says the subject holds something.
 *
 * **Nothing here decides who may see or change anything.** The request goes out identically for
 * every caller; the API answers from grants this browser never receives; `editable` decides
 * whether the form and the removal buttons are drawn and decides nothing else, and every write
 * is refused or accepted by the route whatever this file believed. See
 * `governQuery.A_HIDDEN_CONTROL_IS_NOT_A_REFUSAL`.
 *
 * **A write is followed by a fresh request rather than by a local update.** The listing is
 * keyed on a counter this file bumps, so a successful grant or removal remounts it and it asks
 * again. Patching the row in place would show what the console sent, and what the console sent
 * is not what the database holds: the grant's id and its instant are both the database's, and a
 * removal's effect on what a person reaches is the resolver's answer rather than this page's.
 *
 * **The scope names in the form are the Scopes screen's own answer.** This page asks
 * `/govern/scopes` for them, so what a grantor may choose from is a listing the API already
 * narrowed to them. It narrows nothing on its own; see
 * `governQuery.A_SCOPE_IS_CHOSEN_BY_NAME_AND_NEVER_TYPED`.
 *
 * **The form library is the records screen's, so this route is code-split.** `@rjsf/core` with
 * the ajv validator is the largest thing in this console by a wide margin, and a second eager
 * import of it would put it back in the entry chunk for everybody including a person who only
 * opens the overview. `App.tsx` loads this route on demand and `tests/bundle-split.test.ts`
 * walks the static import graph to prove it.
 *
 * **The data steward card sits under the listing**, because a grant of a data read begins with the
 * steward and an install set up before the setup wizard named one names them here. See
 * `components/DataStewardCard.tsx`.
 *
 * Task ids: M27.7.3, M27.7.7, M27.8.4, M27.9.9, M1.4.3
 */

import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { ConfirmAction } from "../components/ConfirmAction";
import { DataStewardCard } from "../components/DataStewardCard";
import { SchemaForm } from "../components/SchemaForm";
import {
  GRANTS_API_PATH,
  PACK_ASSIGNMENT_API_PATH,
  PACK_UI,
  PACKS_API_PATH,
  packSchema,
  readPacks,
  submittedPack,
  PROPOSAL_UI,
  REMOVAL_API_PATH,
  PEOPLE_API_PATH,
  PEOPLE_FILTERS,
  PEOPLE_SORTS,
  subjectApiPath,
  personIn,
  principalIn,
  proposalSchema,
  readPeoplePage,
  readScopesPage,
  scopeChoicesApiPath,
  subjectAddress,
  submittedProposal,
  type PersonRow,
} from "./governQuery";
import { FailureNotice } from "../ui/FailureNotice";

export const PEOPLE_HEADING = "People and grants";

/** Under the heading. Says what the list is, and nothing about what it is not. */
export const PEOPLE_LEDE =
  "Everybody holding a grant here, and what each of them holds. Open a subject to write a " +
  "grant or take one away.";

/** An empty listing, whichever of the reasons it is empty. */
export const NO_PEOPLE = "There are no subjects to show.";

/** A page that came back full. A fact about there being more, and never a figure. */
export const MORE_PEOPLE = "This page came back full, so there are more subjects than it shows.";

/**
 * What is said when the address names a subject this page does not carry.
 *
 * About this page and not about the estate, which is what makes it safe to say at all: it is
 * the same sentence for a subject who does not exist, one whose grants this reader may not see,
 * and one who has simply dropped off a full page. A sentence that distinguished any two of
 * those would be the oracle the deep link is written to avoid.
 */
export const NO_SUCH_SUBJECT = "No subject you may see has that key.";
export const NONE_MATCH = NOTHING_MATCHES;
export const FILTERS_LABEL = "Narrow the subjects";

/**
 * What is said on a subject whose key is not a principal's.
 *
 * A team holds grants, `gate.capability_grant` has a `principal_id` column and no column for a
 * team, and the removal route names a principal. So a team's row is one this console can show
 * and cannot offer a control on, and saying so is better than drawing a button that is refused.
 */
export const ONLY_A_PERSONS_GRANT_CAN_BE_REMOVED_HERE =
  "This subject is not a person, so a grant of theirs cannot be removed from this screen.";

/** What a grant written here carries, said out loud because the form has no control for it. */
export const A_GRANT_WRITTEN_HERE_DOES_NOT_LAPSE =
  "A grant written here has no expiry. This screen has no control for one yet, so it stands " +
  "until somebody removes it.";

/** The accessible names of the two lists. */
export const PEOPLE_LIST_LABEL = "Subjects holding a grant";
export const HELD_LIST_LABEL = "What this subject holds";

/** What the removal button says. The capability is in its accessible name, not only beside it. */
export function removeLabel(capability: string): string {
  return `Remove ${capability}`;
}

/** The removal's confirmation, naming the capability and the subject it is taken from. */
export function removeQuestion(subject: string, capability: string): string {
  return `Remove ${capability} from ${subject}?`;
}

/**
 * What a removal does. The route retires the grant row rather than deleting it, and the resolver
 * answers from live rows, so the next request is the first one answered without it.
 */
export const REMOVAL_CONSEQUENCE =
  "The grant is retired, so the next request this subject makes is answered without it. The " +
  "retired row is kept, and writing the grant again is how it is given back.";

/** The confirmation's two buttons. */
export const REMOVE_GRANT = "Remove the grant";
export const KEEP_GRANT = "Keep it";

/**
 * One subject's capabilities, each with the control that takes it away.
 *
 * A separate component because it holds the state of one removal in flight and the listing does
 * not. Merging the two would put a busy flag belonging to a write on a component whose other
 * job is rendering a read, and the first person to reuse it would find the list greyed out
 * while somebody clicked.
 */
function HeldCapabilities({
  person,
  editable,
  onWritten,
}: {
  readonly person: PersonRow;
  /**
   * Whether the API said this caller may write a grant. The removal control is drawn only
   * when it is true, exactly as the form is, because both are the same authority:
   * `brain.govern_routes` checks `approve:grant` on the write and on the removal. A control
   * drawn without it is a button whose every press is refused, which is worse than no button.
   */
  readonly editable: boolean;
  readonly onWritten: () => void;
}) {
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  // The capability whose removal is waiting on its confirmation. Taking a grant away ends what it
  // reached, so the button asks and only the confirmation sends: see
  // `tests/destructive-confirmed.test.ts`.
  const [asking, setAsking] = useState<string | null>(null);
  // Two different absences and they are kept apart. A subject that is not a person is a fact
  // about the row and is said out loud, because a reader looking for the button deserves to
  // know why there is none; a caller who may not write is a fact about them, and nothing is
  // said, because a sentence there would be this console describing a refusal the API never
  // made. Folding the two into one null draws the wrong sentence for the commoner case.
  const principalId = principalIn(person.subject);
  const removable = editable ? principalId : null;

  const take = useCallback(
    (capability: string) => {
      if (removable === null) {
        return;
      }
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(REMOVAL_API_PATH, {
          method: "POST",
          body: { principal_id: removable, capability },
        });
        setBusy(false);
        setAsking(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onWritten();
      })();
    },
    [removable, onWritten],
  );

  if (person.capabilities.length === 0) {
    // Nothing, and deliberately not a sentence. An empty list here means the subject holds
    // nothing or that this reader may not be told, and any words at all would pick one.
    return null;
  }

  return (
    <>
      {failure === null ? null : (
        <FailureNotice failure={failure} />
      )}
      {asking === null ? null : (
        <ConfirmAction
          question={removeQuestion(person.subject, asking)}
          consequence={REMOVAL_CONSEQUENCE}
          confirmLabel={REMOVE_GRANT}
          cancelLabel={KEEP_GRANT}
          busy={busy}
          onConfirm={() => {
            take(asking);
          }}
          onCancel={() => {
            setAsking(null);
          }}
        />
      )}
      <ul className="roster" aria-label={HELD_LIST_LABEL}>
        {person.capabilities.map((capability) => (
          <li key={capability}>
            <code>{capability}</code>{" "}
            {removable === null ? null : (
              <button
                type="button"
                className="button"
                disabled={busy || asking !== null}
                onClick={() => {
                  setFailure(null);
                  setAsking(capability);
                }}
              >
                {removeLabel(capability)}
              </button>
            )}
          </li>
        ))}
      </ul>
      {editable && principalId === null ? (
        <p className="note">{ONLY_A_PERSONS_GRANT_CAN_BE_REMOVED_HERE}</p>
      ) : null}
    </>
  );
}

/**
 * The form one grant is written through.
 *
 * Its scope names come from a request of its own, so a reader whose Scopes screen is empty gets
 * a free-text slug rather than an empty dropdown: `proposalSchema` leaves the enumeration off
 * when there is nothing to offer, which keeps the form usable on an install whose scopes this
 * reader cannot list while leaving the route to refuse whatever is typed.
 */
function GrantForm({ subject, onWritten }: { readonly subject: string; readonly onWritten: () => void }) {
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const scopes = useResource<unknown>(scopeChoicesApiPath());
  const slugs = useMemo(
    () => readScopesPage(scopes.data).scopes.map((one) => one.slug),
    [scopes.data],
  );
  const schema = useMemo(() => proposalSchema(slugs), [slugs]);
  const principalId = principalIn(subject);

  const write = useCallback(
    (submitted: unknown) => {
      const proposal = submittedProposal(submitted);
      if (proposal === null) {
        // Not a proposal this screen recognises. Doing nothing is the answer: a write built out
        // of values nobody read is a write nobody meant to make, and a grant is the most
        // expensive wrong write in this console.
        return;
      }
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(GRANTS_API_PATH, {
          method: "POST",
          body: proposal,
        });
        setBusy(false);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        // The answer is discarded and the listing is asked again. The route returns the stored
        // row and this could render it, but then the row in the list and the row in the form
        // would be two copies of one thing that can disagree.
        onWritten();
      })();
    },
    [onWritten],
  );

  return (
    <section className="card">
      <SchemaForm
        caption={`Write a grant for ${subject}`}
        schema={schema}
        uiSchema={PROPOSAL_UI}
        formData={principalId === null ? {} : { principal_id: principalId }}
        failure={failure}
        busy={busy}
        onSubmit={write}
      />
      <p className="note">{A_GRANT_WRITTEN_HERE_DOES_NOT_LAPSE}</p>
    </section>
  );
}

/**
 * The form a capability pack is assigned through (M1.4.3). Every grant the pack means must be one
 * this caller could write on its own, which the route decides; the pack and scope lists are what
 * this reader was answered, so the ordinary case needs no typing.
 */
function PackForm({ subject, onWritten }: { readonly subject: string; readonly onWritten: () => void }) {
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const scopes = useResource<unknown>(scopeChoicesApiPath());
  const packs = useResource<unknown>(PACKS_API_PATH);
  const schema = useMemo(
    () =>
      packSchema(
        readPacks(packs.data).map((one) => one.slug),
        readScopesPage(scopes.data).scopes.map((one) => one.slug),
      ),
    [packs.data, scopes.data],
  );
  const principalId = principalIn(subject);

  const write = useCallback(
    (submitted: unknown) => {
      const proposal = submittedPack(submitted);
      if (proposal === null) {
        return;
      }
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(PACK_ASSIGNMENT_API_PATH, {
          method: "POST",
          body: proposal,
        });
        setBusy(false);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onWritten();
      })();
    },
    [onWritten],
  );

  return (
    <section className="card">
      <SchemaForm
        caption={`Assign a pack to ${subject}`}
        schema={schema}
        uiSchema={PACK_UI}
        formData={principalId === null ? {} : { principal_id: principalId }}
        failure={failure}
        busy={busy}
        onSubmit={write}
      />
    </section>
  );
}

/**
 * The listing itself, and the open subject beside it.
 *
 * The list is `useListing`'s, so its search, its capability filter, its order and "Show more" are
 * requests. The open subject is a request of its own, filtered to the key in the address, so it is
 * found whichever page it would sit on. A successful write moves `version` and both are asked again.
 */
function PeopleRows({
  openSubject,
  version,
  onWritten,
}: {
  readonly openSubject: string | undefined;
  readonly version: number;
  readonly onWritten: () => void;
}) {
  const listing = useListing<PersonRow>(PEOPLE_API_PATH, { choices: PEOPLE_FILTERS, version });
  const opened = useResource<unknown>(openSubject === undefined ? null : subjectApiPath(openSubject), version);

  const page = readPeoplePage(listing.body);
  const openPage = readPeoplePage(opened.data);
  const open = openSubject === undefined ? null : personIn(openPage.people, openSubject);

  return (
    <>
      <ListControls label={FILTERS_LABEL} listing={listing} choices={PEOPLE_FILTERS} sorts={PEOPLE_SORTS} />
      {listing.failure ? (
        <FailureNotice failure={listing.failure} />
      ) : listing.busy ? (
        <p className="note" role="status">
          Loading.
        </p>
      ) : page.people.length === 0 ? (
        <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_PEOPLE}</p>
      ) : (
        <>
          <ul className="roster" aria-label={PEOPLE_LIST_LABEL}>
            {page.people.map((person) => (
              <li key={person.subject}>
                <Link to={subjectAddress(person.subject)}>{person.subject}</Link>{" "}
                {person.capabilities.map((capability) => (
                  <code key={capability}>{capability}</code>
                ))}
              </li>
            ))}
          </ul>
          <ShowMore listing={listing} />
        </>
      )}

      {page.truncated ? <p className="note">{MORE_PEOPLE}</p> : null}

      {opened.failure ? <FailureNotice failure={opened.failure} /> : null}

      {open === null ? null : (
        <section className="card">
          <h2>{open.subject}</h2>
          <HeldCapabilities person={open} editable={openPage.editable} onWritten={onWritten} />
        </section>
      )}

      {/*
       * The form appears when a subject is open and this caller may write a grant. When they
       * may not, nothing is rendered and nothing is said: a sentence explaining that they
       * cannot would be this console describing a refusal the API never made, and the API's
       * refusal, when a write is attempted, is the same one it gives somebody who may not read
       * the screen at all.
       */}
      {open !== null && openPage.editable ? (
        <>
          <GrantForm subject={open.subject} onWritten={onWritten} />
          <PackForm subject={open.subject} onWritten={onWritten} />
        </>
      ) : null}

      {openSubject !== undefined && !opened.busy && opened.failure === null && open === null ? (
        <p className="note">{NO_SUCH_SUBJECT}</p>
      ) : null}
    </>
  );
}

export function People() {
  const { subject } = useParams();
  // A counter rather than a boolean, because two writes in a row must remount twice. Its value
  // is never rendered: it is a key, and a key that reached the screen would be a number
  // describing how many times somebody had written something.
  const [version, setVersion] = useState(0);
  const onWritten = useCallback(() => {
    setVersion((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <h1>{PEOPLE_HEADING}</h1>
      <p className="lede">{PEOPLE_LEDE}</p>

      <PeopleRows openSubject={subject} version={version} onWritten={onWritten} />

      {/*
       * Who every read of the company's data begins with, and naming them where nobody is. Below
       * the listing, and drawn only for a reader the API answers. See `components/DataStewardCard`.
       */}
      <DataStewardCard />
    </article>
  );
}
