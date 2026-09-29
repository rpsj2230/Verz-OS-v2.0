/**
 * Referred to me, on the shared page kit: the sensitive questions routed to the person reading, as
 * notes that somebody asked, each marked handled once the person has been contacted.
 *
 * An agent does not answer a question on a sensitive topic. The asker is told one sentence whatever
 * the topic, and a note goes to the person named for it on the Compliance page. This is where that
 * person reads their notes, under Use beside their own work: being named for grievances is not an
 * administrative grant, and the route asks for none.
 *
 * **There is no question to show, and the page shows nothing in its place.** A referral records who
 * asked, when and about which topic; what they wrote was never stored, and a column for it, even
 * empty, would read as something withheld rather than something that does not exist.
 *
 * **Who asked is a name** (`brain.people_names`), because the reader has to contact them.
 * **Marking one handled is confirmed**, because it cannot be undone from here, and the route answers
 * with the list as it now stands, which the page draws.
 *
 * Task ids: M24.2.2, M27.16.1
 */

import { HeartHandshake, MoreHorizontal } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  Note,
  PageHeader,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { handledApiPath, REFERRALS_API_PATH, type Referral } from "../referralsQuery";
import { nameOf, peopleIn, Pill, whenWords } from "../review/parts";

export const REFERRALS_HEADING = "Referred to me";
export const REFERRALS_LEDE =
  "Notes that somebody asked about a sensitive topic you are named for. What they wrote is not kept; contact them directly, outside their reporting line.";
export const READING_REFERRALS = "Reading what has been referred to you.";
export const NOTHING_REFERRED = "Nothing has been referred to you";
export const NOTHING_REFERRED_MORE = "A note appears here when somebody asks about a topic you are named for on the Compliance page.";
export const REFERRALS_CAPTION = "Questions referred to you";
export const HANDLED_LABEL = "Mark handled";
export const LEAVE_OPEN = "Leave it open";
export const HANDLING =
  "It is recorded as handled by you, now, and stays on this list as handled. It cannot be reopened from here.";

export function handledQuestion(one: Referral, people: Readonly<Record<string, string>>): string {
  return `Mark the ${one.label} referral from ${nameOf(people, one.asked_by)}, asked ${whenWords(one.asked_at)}, handled?`;
}

export function ReferralsPage() {
  const [version, setVersion] = useState(0);
  const [pending, setPending] = useState<Referral | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<unknown>(REFERRALS_API_PATH, version);
  const people = peopleIn(answer.data);
  const referrals: readonly Referral[] =
    typeof answer.data === "object" && answer.data !== null && Array.isArray((answer.data as { referrals?: unknown }).referrals)
      ? ((answer.data as { referrals: Referral[] }).referrals)
      : [];

  const markHandled = useCallback(
    (one: Referral) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(handledApiPath(one.referral_id), { method: "POST" });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        setTold(`The ${one.label} referral from ${nameOf(people, one.asked_by)} is marked handled.`);
        setVersion((count) => count + 1);
      })();
    },
    [people],
  );

  const columns: readonly EntityColumn<Referral>[] = [
    { id: "topic", header: "Topic", hideable: false, cell: (one) => <span className="font-medium text-ink">{one.label}</span>, text: (one) => one.label },
    { id: "asked_by", header: "Asked by", cell: (one) => nameOf(people, one.asked_by), text: (one) => nameOf(people, one.asked_by) },
    { id: "asked", header: "Asked", className: "whitespace-nowrap", cell: (one) => whenWords(one.asked_at), text: (one) => whenWords(one.asked_at) },
    {
      id: "state",
      header: "Where it stands",
      cell: (one) =>
        one.handled_at === null ? (
          <Pill tone="warn">Open</Pill>
        ) : (
          <span className="flex flex-col gap-0.5">
            <span>
              <Pill tone="ok">Handled</Pill>
            </span>
            <span className="text-[12px] text-dim">
              {`${whenWords(one.handled_at)}${one.handled_by === null ? "" : `, by ${nameOf(people, one.handled_by)}`}`}
            </span>
          </span>
        ),
      text: (one) => (one.handled_at === null ? "Open" : `Handled ${whenWords(one.handled_at)}`),
    },
  ];

  let body: ReactNode;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label={READING_REFERRALS} rows={2} />;
  } else if (referrals.length === 0) {
    body = <EmptyState title={NOTHING_REFERRED} description={NOTHING_REFERRED_MORE} icon={<HeartHandshake aria-hidden />} />;
  } else {
    body = (
      <EntityTable
        caption={REFERRALS_CAPTION}
        columns={columns}
        rows={referrals}
        rowId={(one) => one.referral_id}
        rowLabel={(one) => `${one.label}, ${nameOf(people, one.asked_by)}`}
        rowActions={(one) =>
          one.handled_at !== null ? null : (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for the ${one.label} referral from ${nameOf(people, one.asked_by)}`}>
                  <MoreHorizontal aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem
                  disabled={busy}
                  onSelect={() => {
                    setFailure(null);
                    setTold(null);
                    setPending(one);
                  }}
                >
                  {HANDLED_LABEL}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )
        }
      />
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: REFERRALS_HEADING }]} title={REFERRALS_HEADING} lede={REFERRALS_LEDE} />
      {failure === null ? null : <FailureState failure={failure} />}
      {told === null ? null : (
        <div role="status">
          <Note kind="works">{told}</Note>
        </div>
      )}
      <section aria-label={REFERRALS_CAPTION} className="flex min-w-0 flex-col gap-3 rounded-md border border-line bg-panel p-3 sm:p-4">
        {body}
      </section>
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : handledQuestion(pending, people)}
        consequence={HANDLING}
        confirmLabel={HANDLED_LABEL}
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
    </div>
  );
}
