/**
 * The Webhooks list, on the page kit: every system outside the company this install tells when
 * something happens, where it is told, whether its signing secret is held, and when it was last
 * delivered to, with registering one from the header.
 *
 * **A list answered whole, so no search box.** `GET /api/v1/webhooks` takes no search, filter or
 * cursor, and the list is short, so this is `kit/EntityTable` in a card with its column choice and
 * export, which is `operations/parts.tsx`' rule: a search box the route ignores is a control that
 * reaches nothing. The old screen narrowed the rows in the browser instead.
 *
 * **A reader who may not manage subscribers is shown what an empty install shows**, the API's rule
 * (`brain.console.subscribers`), with the one sentence saying what managing them needs, which is a
 * fact about the reader and none about what exists.
 *
 * **What was removed from the old screen, and why.** The principal id beside every subscriber (a
 * name on its page now, the id under Advanced); a card per subscriber under the table repeating its
 * deliveries and changes (its Dashboard and About now); the registration and replacement forms
 * always open under the list (drawers now, opened from the header and the row); the table of
 * arriving channels and their signature checks, which is each channel's About view now; and the
 * automations' address, under Advanced.
 *
 * Task ids: M27.8.12, M27.16.1
 */

import { MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Advanced, EmptyState, Fact, FactList, Note, SectionCard, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { GROUP_LABEL } from "../channelsQuery";
import { at, Line, OpsPage, WholeList } from "../operations/parts";
import {
  WEBHOOKS_API_PATH,
  readWebhooks,
  secretWord,
  webhookAddress,
  type DispatcherBody,
  type SubscriberRow,
  type WebhooksBody,
} from "../webhooksQuery";
import { ACT_LABELS } from "./webhookActions";
import { RegisterDrawer, ReplaceSecretDrawer, SwitchOffDialog } from "./WebhookActs";
import { OFF_WORD, ON_WORD, SubscriberPill } from "./pills";

export const WEBHOOKS_HEADING = "Webhooks";
export const WEBHOOKS_LEDE = "Systems outside the company told when something happens here. They are sent identifiers, never content.";
export const READING_WEBHOOKS = "Loading the webhook subscribers.";
export const NO_SUBSCRIBERS = "No subscribers yet";
export const NO_SUBSCRIBERS_DESCRIPTION = "Register one to tell a system outside the company when something happens here.";
export const NOT_MANAGEABLE_TITLE = "No subscribers to show";
export const NOT_MANAGEABLE = "Registering and changing webhook subscribers needs the webhook management grant over the whole company.";
export const SUBSCRIBERS_HEADING = "Subscribers";
export const DELIVERY_HEADING = "Delivery";
export const NEVER_DELIVERED = "Never";

/** What a drawer or dialog is open for. */
export type OpenAct =
  | { readonly act: "register" }
  | { readonly act: "replace"; readonly id: string }
  | { readonly act: "switch_off"; readonly id: string };

/** How the dispatch's last run ended, in words. */
export function lastRunWords(dispatcher: DispatcherBody): string {
  if (dispatcher.last_started_at === null) {
    return "Not run yet";
  }
  if (dispatcher.last_finished_at === null) {
    return `Started ${at(dispatcher.last_started_at)}, not finished`;
  }
  return `${dispatcher.last_outcome === "failed" ? "Failed" : "Finished"} ${at(dispatcher.last_finished_at)}`;
}

function RowMenu({ row, onAct }: { readonly row: SubscriberRow; readonly onAct: (act: OpenAct) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.subscriber_id}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem asChild>
          <Link to={webhookAddress(row.subscriber_id)}>{ACT_LABELS.open}</Link>
        </DropdownMenuItem>
        {row.active ? (
          <>
            <DropdownMenuItem
              onSelect={() => {
                onAct({ act: "replace", id: row.subscriber_id });
              }}
            >
              {ACT_LABELS.replace}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-crit"
              onSelect={() => {
                onAct({ act: "switch_off", id: row.subscriber_id });
              }}
            >
              {ACT_LABELS.switchOff}
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const COLUMNS: readonly EntityColumn<SubscriberRow>[] = [
  {
    id: "subscriber",
    header: "Subscriber",
    hideable: false,
    cell: (row) => (
      <Link
        to={webhookAddress(row.subscriber_id)}
        className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline"
      >
        {row.subscriber_id}
      </Link>
    ),
    text: (row) => row.subscriber_id,
  },
  {
    id: "endpoint",
    header: "Told at",
    cell: (row) => <span className="font-mono text-[12px]">{row.endpoint}</span>,
    text: (row) => row.endpoint,
  },
  { id: "kinds", header: "Told about", cell: (row) => row.kinds.join(", "), text: (row) => row.kinds.join(", ") },
  {
    id: "state",
    header: "State",
    cell: (row) => <SubscriberPill active={row.active} />,
    text: (row) => (row.active ? ON_WORD : OFF_WORD),
  },
  { id: "secret", header: "Signing secret", cell: (row) => secretWord(row), text: (row) => secretWord(row) },
  {
    id: "delivered",
    header: "Last delivered",
    cell: (row) => (row.last_delivered_at === null ? NEVER_DELIVERED : at(row.last_delivered_at)),
    text: (row) => (row.last_delivered_at === null ? NEVER_DELIVERED : at(row.last_delivered_at)),
  },
];

function Body({ page, onAct }: { readonly page: WebhooksBody; readonly onAct: (act: OpenAct) => void }) {
  if (!page.manageable) {
    return <EmptyState title={NOT_MANAGEABLE_TITLE} description={NOT_MANAGEABLE} />;
  }
  const dispatcher = page.dispatcher;
  return (
    <>
      {page.vault === "ready" ? null : <Note kind="not-yet">{page.vault_told}</Note>}
      <WholeList
        title={SUBSCRIBERS_HEADING}
        caption={SUBSCRIBERS_HEADING}
        columns={COLUMNS}
        rows={page.subscribers}
        rowId={(row) => row.subscriber_id}
        rowLabel={(row) => row.subscriber_id}
        rowActions={(row) => <RowMenu row={row} onAct={onAct} />}
        exportName="webhook-subscribers"
        empty={NO_SUBSCRIBERS}
        emptyDescription={NO_SUBSCRIBERS_DESCRIPTION}
      />
      {page.findings.length === 0 ? null : (
        <div className="flex flex-col gap-1">
          {page.findings.map((one) => (
            <Note key={one}>{one}</Note>
          ))}
        </div>
      )}
      <SectionCard title={DELIVERY_HEADING} lede={dispatcher?.told} footer={<Line>{page.delivery}</Line>}>
        {dispatcher === null ? (
          <Line>{page.delivery}</Line>
        ) : (
          <FactList>
            <Fact label="Last run">{lastRunWords(dispatcher)}</Fact>
            {dispatcher.last_report === null ? null : <Fact label="What it did">{dispatcher.last_report}</Fact>}
          </FactList>
        )}
      </SectionCard>
      <Advanced>
        <FactList>
          <Fact label="Automations call in at">
            <span className="font-mono text-[12px]">{page.inbound.automation_path}</span>
          </Fact>
        </FactList>
        <Line>{page.inbound.automation_told}</Line>
      </Advanced>
    </>
  );
}

export function WebhooksPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const [open, setOpen] = useState<OpenAct | null>(null);
  const answer = useResource<unknown>(WEBHOOKS_API_PATH, version);
  const page = answer.data === null ? null : readWebhooks(answer.data);

  const done = useCallback((sentence: string) => {
    setOpen(null);
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);
  const close = useCallback(() => {
    setOpen(null);
  }, []);
  const act = useCallback((next: OpenAct) => {
    setTold(null);
    setOpen(next);
  }, []);

  return (
    <>
      <OpsPage
        crumbs={[{ label: GROUP_LABEL }, { label: WEBHOOKS_HEADING }]}
        title={WEBHOOKS_HEADING}
        lede={WEBHOOKS_LEDE}
        primary={
          page?.manageable === true ? (
            <Button
              className="min-h-11 sm:min-h-9"
              onClick={() => {
                act({ act: "register" });
              }}
            >
              <Plus aria-hidden />
              {ACT_LABELS.register}
            </Button>
          ) : undefined
        }
        notice={told === null || told === "" ? undefined : <Note kind="done">{told}</Note>}
        loading={READING_WEBHOOKS}
        busy={answer.busy}
        failure={answer.failure}
        body={page}
      >
        {(body) => <Body page={body} onAct={act} />}
      </OpsPage>
      {page === null || open === null ? null : open.act === "register" ? (
        <RegisterDrawer page={page} onClose={close} onDone={done} />
      ) : open.act === "replace" ? (
        <ReplaceSecretDrawer page={page} subscriberId={open.id} onClose={close} onDone={done} />
      ) : (
        <SwitchOffDialog page={page} subscriberId={open.id} onClose={close} onDone={done} />
      )}
    </>
  );
}
