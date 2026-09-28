/**
 * A person's sign-ins: the account they sign in with, and the sessions open now, with the acts that
 * end one, end all of them, and unlink the account.
 *
 * **Each half is its own screen's route, filtered to this person.** The link is the Sign-in links
 * screen's (`/govern/sign-ins`) and the sessions the Sessions screen's (`/govern/sessions`), so what
 * this view shows is exactly what those screens would show this reader about this person, each
 * decided by its own module on the server; a reader who may not open one sees that route's refusal
 * in its place, in its own words.
 *
 * **Ending every session is one confirmed act** (M27.15.25), sent to `/govern/sessions/end-several`,
 * which ends each through the single ending's own decision and says each one's outcome. Ending a
 * session is one sitting and not the person: their grants still hold, and disabling is the header's
 * act.
 *
 * **An account is linked from here too**, through the Sign-in links screen's own route and rule: the
 * account is typed once and never kept, and the person is this page's, so nobody copies an id.
 *
 * Task ids: M27.11.2, M27.16.1
 */

import { LogIn } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
  Drawer,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { LINK_API_PATH, linkOutcome, linkProblems } from "../signInLinksQuery";
import { Field, FormProblem, dayWords, whenWords } from "../access/formParts";
import { SecondFactorPill } from "./pills";
import {
  END_SESSIONS_API_PATH,
  END_SESSION_API_PATH,
  SESSIONS_API_PATH,
  SIGN_INS_API_PATH,
  UNLINK_API_PATH,
  aboutPerson,
  readLink,
  readSessions,
  type PersonDetail,
} from "./peopleQuery";

export const LINK_HEADING = "Sign-in account";
export const SESSIONS_HEADING = "Open sessions";
export const NOT_LINKED = "No sign-in account is linked to them that you may see.";
export const NO_SESSIONS = "No open session you may see.";
export const END_ALL = "End every session";

export const ENDING_DOES =
  "That sitting ends at once and their next request with it is refused. Their grants and their account are untouched; they can sign in again.";
export const ENDING_ALL_DOES =
  "Every sitting listed ends at once. Their grants and their account are untouched; they can sign in again.";
export const UNLINKING_DOES =
  "The account can no longer sign in as this person. Their grants stay, and linking an account again is done on the Sign-in links screen.";

/** Which of the three acts a confirmed control sends. */
type Act =
  | { readonly kind: "end"; readonly sessionId: string }
  | { readonly kind: "endAll"; readonly sessionIds: readonly string[] }
  | { readonly kind: "unlink"; readonly principalId: string };

/** One act, pressed, confirmed in a dialog, and only then sent. */
function Confirmed({
  label,
  ariaLabel,
  question,
  consequence,
  act,
  onDone,
}: {
  readonly label: string;
  readonly ariaLabel?: string | undefined;
  readonly question: string;
  readonly consequence: string;
  readonly act: Act;
  readonly onDone: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const go = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result =
        act.kind === "end"
          ? await request<unknown>(END_SESSION_API_PATH, { method: "POST", body: { session_id: act.sessionId } })
          : act.kind === "endAll"
            ? await request<unknown>(END_SESSIONS_API_PATH, { method: "POST", body: { session_ids: act.sessionIds } })
            : await request<unknown>(UNLINK_API_PATH, { method: "POST", body: { principal_id: act.principalId } });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onDone();
    })();
  }, [act, onDone]);
  return (
    <span className="flex flex-col items-end gap-1">
      <Button
        size="sm"
        variant="outline"
        aria-label={ariaLabel}
        onClick={() => {
          setFailure(null);
          setAsking(true);
        }}
      >
        {label}
      </Button>
      {failure === null ? null : <FailureState failure={failure} />}
      <ConfirmDialog
        open={asking}
        question={question}
        consequence={consequence}
        confirmLabel={label}
        cancelLabel="Leave it"
        busy={busy}
        onConfirm={go}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </span>
  );
}

/**
 * An identity provider account linked to this person, from their own page, so a person added by
 * hand is linked without anybody copying an id between screens (M27.15.19). The same route and the
 * same rule as the Sign-in links screen: the account is sent once and the field emptied whatever
 * the answer, for `signInLinksQuery.AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT`'s reason.
 * Linking ends nothing, so it is a drawer's submit; unlinking is the confirmed act.
 */
function LinkAccountDrawer({
  open,
  onOpenChange,
  principalId,
  person,
  onLinked,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly principalId: string;
  readonly person: string;
  readonly onLinked: (sentence: string) => void;
}) {
  const [account, setAccount] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found = linkProblems(account, principalId);
    setProblem(found[0] ?? null);
    setFailure(null);
    setRefusal(null);
    if (found.length > 0) {
      return;
    }
    const body = { subject: account, principal_id: principalId };
    setAccount("");
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(LINK_API_PATH, { method: "POST", body });
      setBusy(false);
      if (result.ok) {
        onOpenChange(false);
        onLinked(linkOutcome(result.data) ?? "");
        return;
      }
      setFailure(result.failure);
      setRefusal(result.failure.status === 409 ? linkOutcome(result.body) : null);
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={`Link an account to ${person}`}
      description="The identity provider account they will sign in with. It is sent once and never shown again."
      footer={
        <>
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button type="submit" form="link-account" disabled={busy}>
            Link the account
          </Button>
        </>
      }
    >
      <form id="link-account" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <Field
          label="Account ID"
          hint="Exactly as the identity provider issues it, with no space around it. Copy it from the provider's user list."
          problem={problem}
          apiProblems={failure?.problems ?? []}
          names={["subject"]}
        >
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              autoComplete="off"
              spellCheck={false}
              aria-describedby={describedBy}
              aria-invalid={invalid ? true : undefined}
              className="h-11 font-mono sm:h-9"
              value={account}
              onChange={(event) => {
                setAccount(event.target.value);
              }}
            />
          )}
        </Field>
        {refusal !== null ? <FormProblem>{refusal}</FormProblem> : failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

export function PersonSessions({ detail }: { readonly detail: PersonDetail }) {
  const { person } = detail;
  const [version, setVersion] = useState(0);
  const links = useResource<unknown>(aboutPerson(SIGN_INS_API_PATH, "principal_id", person.principalId), version);
  const sessions = useResource<unknown>(aboutPerson(SESSIONS_API_PATH, "principal_id", person.principalId), version);
  const again = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const [linking, setLinking] = useState(false);
  const [linked, setLinked] = useState<string | null>(null);
  const link = readLink(links.data, person.principalId);
  const open = readSessions(sessions.data, person.principalId);
  const endable = open.filter((one) => one.endable);

  let linkBody;
  if (links.failure !== null) {
    linkBody = <FailureState failure={links.failure} />;
  } else if (links.data === null) {
    linkBody = <LoadingState label="Loading their sign-in account." rows={1} />;
  } else if (link === null) {
    linkBody = <p className="m-0 text-[13px] text-dim">{NOT_LINKED}</p>;
  } else {
    linkBody = (
      <FactList>
        <Fact label="Linked">{link.linkedAt === undefined ? "Yes" : dayWords(link.linkedAt)}</Fact>
        {link.lastAdministrator ? <Fact label="Last way in">The only administrator who can sign in, so it cannot be unlinked.</Fact> : null}
      </FactList>
    );
  }

  let sessionBody;
  if (sessions.failure !== null) {
    sessionBody = <FailureState failure={sessions.failure} />;
  } else if (sessions.data === null) {
    sessionBody = <LoadingState label="Loading their open sessions." rows={2} />;
  } else if (open.length === 0) {
    sessionBody = <EmptyState title={NO_SESSIONS} description="A session appears here from its first request, and goes when it ends or lapses." icon={<LogIn aria-hidden />} />;
  } else {
    sessionBody = (
      <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
        {open.map((one) => (
          <li key={one.sessionId} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="flex min-w-0 flex-wrap items-center gap-2 text-[13px]">
              <span>Signed in {whenWords(one.signedInAt)}</span>
              <SecondFactorPill seen={one.secondFactor} />
              {one.yours ? <span className="text-dim">(this sign-in)</span> : null}
              {one.lapsesAt === undefined ? null : <span className="text-dim">lapses {whenWords(one.lapsesAt)}</span>}
            </span>
            {one.endable ? (
              <Confirmed
                label="End"
                ariaLabel={`End the session that began ${whenWords(one.signedInAt)}`}
                question={`End ${person.displayName}'s session that began ${whenWords(one.signedInAt)}?`}
                consequence={ENDING_DOES}
                act={{ kind: "end", sessionId: one.sessionId }}
                onDone={again}
              />
            ) : null}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title={LINK_HEADING}
        lede="The identity provider account they sign in with. The account itself is kept by the identity provider, not here."
        action={
          link !== null && !link.lastAdministrator ? (
            <Confirmed
              label="Unlink"
              question={`Unlink ${person.displayName}'s sign-in account?`}
              consequence={link.yours ? `${UNLINKING_DOES} You will be signed out.` : UNLINKING_DOES}
              act={{ kind: "unlink", principalId: person.principalId }}
              onDone={again}
            />
          ) : link === null && links.data !== null ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setLinking(true);
              }}
            >
              Link an account
            </Button>
          ) : undefined
        }
      >
        {linkBody}
        {linked === null || linked === "" ? null : (
          <p role="status" className="m-0 mt-2 text-[12.5px] text-ok">
            {linked}
          </p>
        )}
        <LinkAccountDrawer
          open={linking}
          onOpenChange={setLinking}
          principalId={person.principalId}
          person={person.displayName}
          onLinked={(sentence) => {
            setLinked(sentence);
            again();
          }}
        />
      </SectionCard>
      <SectionCard
        title={SESSIONS_HEADING}
        lede="Each sitting they are signed in with now, and whether it carried a second factor."
        action={
          endable.length > 1 ? (
            <Confirmed
              label={END_ALL}
              question={`End every session of ${person.displayName}'s listed here?`}
              consequence={ENDING_ALL_DOES}
              act={{ kind: "endAll", sessionIds: endable.map((one) => one.sessionId) }}
              onDone={again}
            />
          ) : undefined
        }
      >
        {sessionBody}
      </SectionCard>
    </div>
  );
}
