/**
 * Sign-in links, on the shared page kit: which people can sign in and since when, linking an
 * identity provider account to a person, and unlinking one.
 *
 * **The account is never on this page.** The server keeps a one-way fingerprint of it, so a row
 * names the person and the date, and the drawer's form sends a typed account once and empties the
 * field whatever came back (`signInLinksQuery.AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT`).
 *
 * **Unlinking is confirmed; linking is not.** A link replaces nothing, because an account already
 * bound elsewhere is refused with a 409 rather than re-pointed, so it is sent from the drawer's own
 * submit once each field has been checked against what the route takes. The last administrator's
 * link has no unlink control, and if a race makes the store refuse one anyway the 409's own
 * sentence is drawn in the confirmation.
 *
 * Removed in the rebuild: the principal id beside every name, the crumb and the paragraphs that
 * restated the design and the four states, the separate form card under the list (now a drawer
 * from the header, with a hint under each field), and the served sentence about where the account
 * is kept, which moved from under the list into the drawer where an account is typed.
 *
 * Task ids: M27.7.11, M27.8.5, M27.16.1
 */

import { KeyRound, Plus } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { useListing } from "../../components/useListing";
import { Chip, ConfirmDialog, Drawer, ListPage, Note, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  ACCOUNT_HINT,
  LINK_API_PATH,
  LINK_FILTERS,
  LINK_SORTS,
  LINKS_API_PATH,
  MAX_IDENTIFIER_CHARS,
  PERSON_HINT,
  UNLINK_API_PATH,
  linkOutcome,
  linkProblems,
  linkedOn,
  readLinksPage,
  unlinkSentence,
  type LinkAsked,
  type LinkRow,
  type UnlinkAsked,
} from "../signInLinksQuery";

export const LINKS_HEADING = "Sign-in links";
export const LINKS_LEDE = "Who can sign in, and since when.";
export const PEOPLE_AND_ACCESS = "People and access";

export const LOADING_LINKS = "Loading sign-in links.";
export const NO_LINKS = "No sign-in links to show";
export const NO_LINKS_DESCRIPTION = "A person appears here once an identity provider account is linked to them.";
/** A full load. A fact about there being more, and never a figure. */
export const MORE_LINKS = "There are more links than one list can hold. Search or filter to find the rest.";

export const LINKS_LIST_LABEL = "People who can sign in";
export const FILTERS_LABEL = "Narrow the sign-in links";
export const SEARCH_HINT = "Search by name or department";

export const PERSON_COLUMN = "Person";
export const LINKED_COLUMN = "Linked on";
export const DEPARTMENT_COLUMN = "Department";

/** The chips a row may carry: the last way in for an administrator, and the reader's own link. */
export const LAST_ADMINISTRATOR = "Last administrator";
export const YOURS = "You";

export const UNLINK_LABEL = "Unlink";
export const CONFIRM_UNLINK_LABEL = "Unlink this sign-in";
export const KEEP_LABEL = "Keep it";
export const YOUR_OWN_LINK = "This is your own sign-in link. You will be signed out on your next request.";
export const UNLINKING_FALLBACK = "That account stops signing in as this person from their next request.";
export const UNLINKED_FALLBACK = "The sign-in was unlinked.";
export const NOT_UNLINKED = "The sign-in was not unlinked";

export const LINK_A_SIGN_IN = "Link a sign-in";
export const LINK_DESCRIPTION = "Link an identity provider account to a person, so that account signs in as them.";
export const ACCOUNT_LABEL = "Identity provider account ID";
export const PERSON_LABEL = "Person ID";
export const LINK_BUTTON = "Link this account";
export const CLOSE_LABEL = "Close";
export const NOT_LINKED = "The account was not linked";
export const LINKED_FALLBACK = "The account was linked.";

export function unlinkQuestion(row: LinkRow): string {
  return `Unlink ${row.display_name}'s sign-in?`;
}

/** The link form's id, which prefixes its inputs and the lists of problems beside them. */
const LINK_FORM = "sign-in-link";
/** The names the link form's two inputs are sent under. */
const LINK_FIELDS: readonly string[] = ["subject", "principal_id"];

/** A failure, and the sentence its own body carried when it was a 409. */
interface Refused {
  readonly failure: ApiFailure;
  readonly sentence?: string;
}

function RefusedNotice({ refused, title, fields }: { readonly refused: Refused; readonly title: string; readonly fields?: readonly string[] }) {
  return (
    <FailureNotice
      failure={refused.failure}
      title={title}
      {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
      {...(fields === undefined ? {} : { fields })}
    />
  );
}

/** One field of the link form: its label, the input, what it takes, and the API's words about it. */
function LinkField({
  name,
  label,
  hint,
  value,
  problems,
  busy,
  onChange,
}: {
  readonly name: string;
  readonly label: string;
  readonly hint: string;
  readonly value: string;
  readonly problems: readonly FieldProblem[];
  readonly busy: boolean;
  readonly onChange: (value: string) => void;
}) {
  const id = `${LINK_FORM}-${name}`;
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        name={name}
        value={value}
        maxLength={MAX_IDENTIFIER_CHARS}
        autoComplete="off"
        spellCheck={false}
        disabled={busy}
        {...problemAttributes(problems, LINK_FORM, name, hintId)}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <p id={hintId} className="m-0 text-[12.5px] leading-snug text-dim">
        {hint}
      </p>
      <FieldProblems problems={problems} form={LINK_FORM} names={name} />
    </div>
  );
}

function LinkDrawer({
  account,
  onClose,
  onLinked,
}: {
  /** Where the account is kept, in the API's words. */
  readonly account: string;
  readonly onClose: () => void;
  readonly onLinked: (sentence: string) => void;
}) {
  const [subject, setSubject] = useState("");
  const [principalId, setPrincipalId] = useState("");
  const [checked, setChecked] = useState<readonly FieldProblem[]>([]);
  const [refused, setRefused] = useState<Refused | null>(null);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...checked, ...(refused?.failure.problems ?? [])];

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const found = linkProblems(subject, principalId);
    setChecked(found);
    setRefused(null);
    if (found.length > 0) {
      return;
    }
    const body: LinkAsked = { subject, principal_id: principalId.trim() };
    // Emptied before the answer, whatever it is. See AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT.
    setSubject("");
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(LINK_API_PATH, { method: "POST", body });
      setBusy(false);
      if (result.ok) {
        setPrincipalId("");
        onLinked(linkOutcome(result.data) ?? LINKED_FALLBACK);
        return;
      }
      const sentence = result.failure.status === 409 ? linkOutcome(result.body) : null;
      setRefused(sentence === null ? { failure: result.failure } : { failure: result.failure, sentence });
    })();
  }

  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose();
        }
      }}
      title={LINK_A_SIGN_IN}
      description={LINK_DESCRIPTION}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {CLOSE_LABEL}
          </Button>
          <Button type="submit" form={LINK_FORM} disabled={busy}>
            {LINK_BUTTON}
          </Button>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        {account === "" ? null : <Note>{account}</Note>}
        {refused === null ? null : <RefusedNotice refused={refused} title={NOT_LINKED} fields={LINK_FIELDS} />}
        <form id={LINK_FORM} aria-label={LINK_A_SIGN_IN} className="flex flex-col gap-4" noValidate autoComplete="off" onSubmit={submit}>
          <LinkField
            name="subject"
            label={ACCOUNT_LABEL}
            hint={ACCOUNT_HINT}
            value={subject}
            problems={problems}
            busy={busy}
            onChange={setSubject}
          />
          <LinkField
            name="principal_id"
            label={PERSON_LABEL}
            hint={PERSON_HINT}
            value={principalId}
            problems={problems}
            busy={busy}
            onChange={setPrincipalId}
          />
        </form>
      </div>
    </Drawer>
  );
}

export function SignInLinksPage() {
  // Asked again under a new version after a write, so the list shows what the database holds.
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState("");
  const [linking, setLinking] = useState(false);
  const [pending, setPending] = useState<LinkRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<Refused | null>(null);
  const listing = useListing<LinkRow>(LINKS_API_PATH, { choices: LINK_FILTERS, version });
  const page = useMemo(() => readLinksPage(listing.body), [listing.body]);
  const rows = page.links;

  function done(sentence: string): void {
    setLinking(false);
    setPending(null);
    setRefused(null);
    setTold(sentence);
    setVersion((count) => count + 1);
  }

  function unlink(row: LinkRow): void {
    const body: UnlinkAsked = { principal_id: row.principal_id };
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(UNLINK_API_PATH, { method: "POST", body });
      setBusy(false);
      if (result.ok) {
        const sentence = unlinkSentence(result.data);
        done(sentence === "" ? UNLINKED_FALLBACK : sentence);
        return;
      }
      const sentence = result.failure.status === 409 ? unlinkSentence(result.body) : "";
      setRefused(sentence === "" ? { failure: result.failure } : { failure: result.failure, sentence });
    })();
  }

  const columns: readonly EntityColumn<LinkRow>[] = [
    {
      id: "person",
      header: PERSON_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[10rem] flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{row.display_name}</span>
            {row.yours ? <Chip tone="brand">{YOURS}</Chip> : null}
            {row.last_administrator ? <Chip>{LAST_ADMINISTRATOR}</Chip> : null}
          </span>
          {row.department === null ? null : <span className="text-[12px] text-dim">{row.department}</span>}
        </span>
      ),
      text: (row) => row.display_name,
    },
    {
      id: "linked",
      header: LINKED_COLUMN,
      cell: (row) => <span className="tabular-nums">{linkedOn(row.linked_at)}</span>,
      text: (row) => linkedOn(row.linked_at),
    },
    {
      id: "department",
      header: DEPARTMENT_COLUMN,
      hidden: true,
      cell: (row) => row.department ?? null,
      text: (row) => row.department ?? "",
    },
  ];

  const lastAdministratorShown = page.lastAdministrator !== "" && rows.some((row) => row.last_administrator);

  return (
    <>
      <ListPage
        crumbs={[{ label: PEOPLE_AND_ACCESS, to: "/people" }, { label: LINKS_HEADING }]}
        title={LINKS_HEADING}
        lede={LINKS_LEDE}
        primary={
          <Button
            className="min-h-11 sm:min-h-8"
            onClick={() => {
              setTold("");
              setLinking(true);
            }}
          >
            <Plus aria-hidden />
            {LINK_A_SIGN_IN}
          </Button>
        }
        notice={
          told === "" ? null : (
            <div role="status">
              <Note>{told}</Note>
            </div>
          )
        }
        listing={listing}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={LINK_FILTERS}
        sorts={LINK_SORTS}
        searchHint={SEARCH_HINT}
        caption={LINKS_LIST_LABEL}
        columns={columns}
        rowId={(row) => row.principal_id}
        rowLabel={(row) => row.display_name}
        rowActions={(row) =>
          row.last_administrator ? null : (
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              aria-label={`${UNLINK_LABEL}: ${row.display_name}`}
              disabled={busy}
              onClick={() => {
                setTold("");
                setRefused(null);
                setPending(row);
              }}
            >
              {UNLINK_LABEL}
            </Button>
          )
        }
        exportName="sign-in-links"
        loading={LOADING_LINKS}
        emptyTitle={NO_LINKS}
        emptyDescription={NO_LINKS_DESCRIPTION}
        emptyIcon={<KeyRound aria-hidden />}
        footer={
          page.truncated || lastAdministratorShown ? (
            <div className="flex flex-col gap-1">
              {lastAdministratorShown ? <Note>{page.lastAdministrator}</Note> : null}
              {page.truncated ? <Note>{MORE_LINKS}</Note> : null}
            </div>
          ) : null
        }
      />
      {pending === null ? null : (
        <ConfirmDialog
          open
          question={unlinkQuestion(pending)}
          consequence={page.unlinking === "" ? UNLINKING_FALLBACK : page.unlinking}
          details={
            pending.yours || refused !== null ? (
              <div className="flex min-w-0 flex-col gap-2">
                {pending.yours ? <Note>{YOUR_OWN_LINK}</Note> : null}
                {refused === null ? null : <RefusedNotice refused={refused} title={NOT_UNLINKED} />}
              </div>
            ) : undefined
          }
          confirmLabel={CONFIRM_UNLINK_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            unlink(pending);
          }}
          onCancel={() => {
            setPending(null);
            setRefused(null);
          }}
        />
      )}
      {linking ? (
        <LinkDrawer
          account={page.account}
          onClose={() => {
            setLinking(false);
          }}
          onLinked={done}
        />
      ) : null}
    </>
  );
}
