/**
 * Access requests on the shared page kit: the requests other people sent the reader to decide, each
 * marked handled once dealt with, and a drawer to ask for access yourself.
 *
 * **The list is the reader's own.** `GET /access-requests` returns only what was addressed to the
 * caller, so no grant opens it and nothing here decides who sees a row. Each row names who asked,
 * by name (`brain.people_names`), what it is about, the capability that would answer it and the
 * question in the asker's words.
 *
 * **Marking one handled is the owner saying they dealt with it** (needs-rupash gap (a)), confirmed
 * because it cannot be undone from here. It grants nothing: the decision is a grant made on the
 * person's own page, which is linked from the confirmation's sentence.
 *
 * **What the asker is told after sending is the API's one sentence**, drawn as it came back,
 * whether a request was stored or not; the page adds nothing that could tell the two apart. Asking
 * is not confirmed: a request ends and replaces nothing.
 *
 * Task ids: M4.3.4, M2.2.4, M27.16.1
 */

import { Inbox, MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { Chip, ConfirmDialog, Drawer, FailureState, ListPage, Note, type EntityColumn } from "../../components/kit";
import { useListing } from "../../components/useListing";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { Field, NativeSelect } from "../access/formParts";
import {
  ACCESS_REQUESTS_API_PATH,
  ACCESS_REQUESTS_LABEL,
  ACCESS_REQUESTS_LEDE,
  acknowledgement,
  ASK_BLANKS,
  ASK_DESCRIPTION,
  ASK_HEADING,
  ASK_HINTS,
  ASK_LABEL,
  askBlanks,
  askBody,
  EMPTY_ASK,
  FILTERS_LABEL,
  handledApiPath,
  NOTHING_SENT,
  NOTHING_SENT_MORE,
  READING_REQUESTS,
  REQUEST_FILTERS,
  REQUEST_SORTS,
  SENT_CAPTION,
  STATE_WORDS,
  subjectWords,
  type AccessAsk,
  type AccessRequestRow,
} from "../accessRequestsQuery";
import { nameOf, peopleIn, Pill, whenWords } from "../review/parts";

export const MARK_HANDLED = "Mark handled";
export const LEAVE_OPEN = "Leave it open";
export const NOT_NOW = "Not now";
export const HANDLING =
  "It is recorded as handled by you, now, and stays on this list as handled. It cannot be reopened from here. Nothing is granted: give access from the person's own page.";
export const MORE_REQUESTS = "There are more requests sent to you than this page shows. Show more, or narrow the list.";

export function handledQuestion(row: AccessRequestRow, people: Readonly<Record<string, string>>): string {
  return `Mark the request from ${nameOf(people, row.asker_id)} about ${subjectWords(row.subject)} handled?`;
}

function handledOf(row: AccessRequestRow): boolean {
  return row.handled_at !== null && row.handled_at !== undefined;
}

const ASK_FORM = "access-ask";

function AskDrawer({ onClose, onTold }: { readonly onClose: () => void; readonly onTold: (told: string) => void }) {
  const [ask, setAsk] = useState<AccessAsk>(EMPTY_ASK);
  const [blanks, setBlanks] = useState<readonly (keyof typeof ASK_BLANKS)[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const apiProblems = failure?.problems ?? [];
  const blank = (name: keyof typeof ASK_BLANKS) => (blanks.includes(name) ? ASK_BLANKS[name] : null);

  const onSend = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = askBlanks(ask);
    setBlanks(missing);
    if (missing.length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(ACCESS_REQUESTS_API_PATH, { method: "POST", body: askBody(ask) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onTold(acknowledgement(result.data) ?? "");
    })();
  };
  const text = (name: "department" | "entity" | "field") => (
    <Field label={{ department: "Department", entity: "Kind of record", field: "Field" }[name]} hint={ASK_HINTS[name]} problem={blank(name)} apiProblems={apiProblems} names={[name]}>
      {({ id, describedBy, invalid }) => (
        <Input
          id={id}
          name={name}
          autoComplete="off"
          aria-describedby={describedBy === "" ? undefined : describedBy}
          aria-invalid={invalid || undefined}
          value={ask[name]}
          onChange={(event) => {
            setAsk({ ...ask, [name]: event.target.value });
          }}
        />
      )}
    </Field>
  );

  return (
    <Drawer
      open
      onOpenChange={(next) => {
        if (!next && !busy) {
          onClose();
        }
      }}
      title={ASK_HEADING}
      description={ASK_DESCRIPTION}
      footer={
        <>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            {NOT_NOW}
          </Button>
          <Button type="submit" form={ASK_FORM} disabled={busy}>
            {ASK_LABEL}
          </Button>
        </>
      }
    >
      <form id={ASK_FORM} aria-label="Ask for access" className="flex min-w-0 flex-col gap-4" noValidate onSubmit={onSend}>
        {failure === null ? null : <FailureState failure={failure} />}
        <Field label="About" hint="A department an answer said you cannot reach, or a field you were shown locked.">
          {(ids) => (
            <NativeSelect
              {...ids}
              value={ask.kind}
              onChange={(value) => {
                setAsk({ ...ask, kind: value === "field" ? "field" : "department" });
              }}
            >
              <option value="department">A department</option>
              <option value="field">A locked field</option>
            </NativeSelect>
          )}
        </Field>
        {ask.kind === "department" ? text("department") : (
          <>
            {text("entity")}
            {text("field")}
          </>
        )}
        <Field label="What you need it for" hint={ASK_HINTS.question} problem={blank("question")} apiProblems={apiProblems} names={["question"]}>
          {({ id, describedBy, invalid }) => (
            <Textarea
              id={id}
              name="question"
              maxLength={2000}
              aria-describedby={describedBy === "" ? undefined : describedBy}
              aria-invalid={invalid || undefined}
              value={ask.question}
              onChange={(event) => {
                setAsk({ ...ask, question: event.target.value });
              }}
            />
          )}
        </Field>
      </form>
    </Drawer>
  );
}

export function AccessRequestsPage() {
  const [version, setVersion] = useState(0);
  const [asking, setAsking] = useState(false);
  const [told, setTold] = useState<string | null>(null);
  const [pending, setPending] = useState<AccessRequestRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const listing = useListing<AccessRequestRow>(ACCESS_REQUESTS_API_PATH, { choices: REQUEST_FILTERS, version });
  const people = useMemo(() => peopleIn(listing.body), [listing.body]);
  const truncated = useMemo(
    () => typeof listing.body === "object" && listing.body !== null && (listing.body as { truncated?: unknown }).truncated === true,
    [listing.body],
  );

  const markHandled = useCallback((row: AccessRequestRow) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(handledApiPath(row.request_id), { method: "POST" });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setTold(`The request from ${nameOf(people, row.asker_id)} is marked handled.`);
      setVersion((count) => count + 1);
    })();
  }, [people]);

  const choices = REQUEST_FILTERS.map((choice) =>
    choice.column === "asker_id" ? { ...choice, describe: (value: string) => nameOf(people, value) } : choice,
  );

  const columns: readonly EntityColumn<AccessRequestRow>[] = [
    {
      id: "asker",
      header: "Asked by",
      hideable: false,
      cell: (row) => <span className="font-medium text-ink">{nameOf(people, row.asker_id)}</span>,
      text: (row) => nameOf(people, row.asker_id),
    },
    {
      id: "about",
      header: "About",
      cell: (row) => subjectWords(row.subject),
      text: (row) => subjectWords(row.subject),
    },
    {
      id: "question",
      header: "Their question",
      cell: (row) => <span className="[overflow-wrap:anywhere]">{row.question}</span>,
      text: (row) => row.question,
    },
    {
      id: "need",
      header: "Would need",
      cell: (row) => <Chip mono>{row.requested_capability}</Chip>,
      text: (row) => row.requested_capability,
    },
    {
      id: "asked",
      header: "Asked",
      className: "whitespace-nowrap",
      cell: (row) => whenWords(row.requested_at),
      text: (row) => whenWords(row.requested_at),
    },
    {
      id: "state",
      header: "Where it stands",
      cell: (row) =>
        handledOf(row) ? (
          <span className="flex flex-col gap-0.5">
            <span>
              <Pill tone="ok">{STATE_WORDS["handled"]}</Pill>
            </span>
            <span className="text-[12px] text-dim">{whenWords(row.handled_at)}</span>
          </span>
        ) : (
          <Pill tone="warn">{STATE_WORDS["open"]}</Pill>
        ),
      text: (row) => (handledOf(row) ? `Handled ${whenWords(row.handled_at)}` : "Open"),
    },
  ];

  return (
    <>
      <ListPage
        crumbs={[{ label: ACCESS_REQUESTS_LABEL }]}
        title={ACCESS_REQUESTS_LABEL}
        lede={ACCESS_REQUESTS_LEDE}
        primary={
          <Button
            size="sm"
            className="min-h-11 sm:min-h-8"
            onClick={() => {
              setTold(null);
              setAsking(true);
            }}
          >
            <Plus aria-hidden /> {ASK_HEADING}
          </Button>
        }
        notice={
          <>
            {failure === null ? null : <FailureState failure={failure} />}
            {told === null || told === "" ? null : (
              <div role="status">
                <Note kind="works">{told}</Note>
              </div>
            )}
          </>
        }
        listing={listing}
        rows={listing.rows}
        filtersLabel={FILTERS_LABEL}
        choices={choices}
        sorts={REQUEST_SORTS}
        searchHint="Search the requests"
        caption={SENT_CAPTION}
        columns={columns}
        rowId={(row) => row.request_id}
        rowLabel={(row) => `${nameOf(people, row.asker_id)}, ${subjectWords(row.subject)}`}
        rowActions={(row) =>
          handledOf(row) ? null : (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for the request from ${nameOf(people, row.asker_id)}`}>
                  <MoreHorizontal aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem
                  disabled={busy}
                  onSelect={() => {
                    setFailure(null);
                    setTold(null);
                    setPending(row);
                  }}
                >
                  {MARK_HANDLED}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )
        }
        exportName="access-requests"
        loading={READING_REQUESTS}
        emptyTitle={NOTHING_SENT}
        emptyDescription={NOTHING_SENT_MORE}
        emptyIcon={<Inbox aria-hidden />}
        footer={truncated ? <Note>{MORE_REQUESTS}</Note> : undefined}
      />
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : handledQuestion(pending, people)}
        consequence={HANDLING}
        confirmLabel={MARK_HANDLED}
        cancelLabel={LEAVE_OPEN}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            markHandled(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
      {asking ? (
        <AskDrawer
          onClose={() => {
            setAsking(false);
          }}
          onTold={(sentence) => {
            setAsking(false);
            setTold(sentence);
          }}
        />
      ) : null}
    </>
  );
}
