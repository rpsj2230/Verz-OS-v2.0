/**
 * One webhook subscriber's page on the shared kit, in SCREEN 14's shape: one header shared by
 * three views, Dashboard, Profile and About, each at its own address.
 *
 * **The addresses.** `/webhooks/{id}` is the Dashboard, `/webhooks/{id}/profile` and
 * `/webhooks/{id}/about` the other two; anything else opens the Dashboard.
 *
 * **One request, the list's own.** `GET /api/v1/webhooks` answers every subscriber a manager may
 * see, and this page draws the one named; there is no route for one subscriber, and a second read
 * of the same rows would be a second place for them to disagree. A reader who may not manage
 * subscribers is sent no rows, so a subscriber that exists and one that does not read the same
 * here: "No subscriber here".
 *
 * **Every act works, confirmed in the API's words** (`WebhookActs.tsx`): replacing the signing
 * secret and switching off while it is on, switching it back on while it is off, and replaying a
 * delivery that was given up, from that delivery's row, by the name the API gave it rather than by
 * its event id (`brain.ops.webhook_store.A_DELIVERY_IS_REPLAYED_BY_A_NAME_OF_ITS_OWN`). A delivery
 * the API offers no name for has no replay control (M27.15.44).
 *
 * **People are named, never shown by id**; the ids are under Advanced.
 *
 * Task ids: M27.8.12, M27.15.44, M27.16.1
 */

import { IdCard, Info, LayoutDashboard } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  DetailHeader,
  DetailPage,
  EmptyState,
  EntityTable,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
  StatCard,
  ViewSwitch,
  type DetailView,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { at, Line } from "../operations/parts";
import {
  CHANGE_LABELS,
  WEBHOOKS_API_PATH,
  WEBHOOKS_PATH,
  personWords,
  readWebhooks,
  secretWord,
  webhookAddress,
  type ChangeRow,
  type DeliveryRow,
  type SubscriberRow,
  type WebhooksBody,
} from "../webhooksQuery";
import { ACT_LABELS } from "./webhookActions";
import { ReplaceSecretDrawer, ReplayDialog, SwitchOffDialog, SwitchOnDialog } from "./WebhookActs";
import { NEVER_DELIVERED, WEBHOOKS_HEADING } from "./WebhooksPage";
import { DeliveryPill, OFF_WORD, ON_WORD, SubscriberPill } from "./pills";

export const VIEWS = ["dashboard", "profile", "about"] as const;
export type WebhookView = (typeof VIEWS)[number];

export const VIEW_LABELS: Readonly<Record<WebhookView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

export const VIEWS_LABEL = "Subscriber views";
export const LOADING_SUBSCRIBER = "Loading this subscriber.";
export const NOT_HERE = "No subscriber here";
export const NOT_HERE_DESCRIPTION = "There is no subscriber at this address that you may manage.";
export const FIGURES_LABEL = "This subscriber at a glance";
export const DELIVERIES_HEADING = "Recent deliveries";
export const NO_DELIVERIES = "Nothing has been sent to it yet";
export const NO_DELIVERIES_DESCRIPTION = "A delivery appears here once something it is told about happens.";
export const CHANGES_HEADING = "History";
export const NO_CHANGES = "No change recorded from the console.";

const VIEW_ICONS: Readonly<Record<WebhookView, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

export function viewAddress(id: string, view: WebhookView): string {
  return view === VIEWS[0] ? webhookAddress(id) : `${webhookAddress(id)}/${view}`;
}

export function viewFor(tab: string | undefined): WebhookView {
  return tab === "profile" || tab === "about" ? tab : "dashboard";
}

type Open = "replace" | "switch_off" | "switch_on" | null;

function deliveryColumns(): readonly EntityColumn<DeliveryRow>[] {
  return [
    { id: "kind", header: "Kind", hideable: false, cell: (row) => row.kind, text: (row) => row.kind },
    { id: "state", header: "Where it got to", cell: (row) => <DeliveryPill state={row.state} />, text: (row) => row.state },
    { id: "attempts", header: "Attempts", cell: (row) => String(row.attempts), text: (row) => String(row.attempts) },
    { id: "last", header: "Last attempt", cell: (row) => at(row.last_attempt_at), text: (row) => at(row.last_attempt_at) },
    { id: "next", header: "Next try", cell: (row) => at(row.next_attempt_at), text: (row) => at(row.next_attempt_at) },
    { id: "why", header: "Why", cell: (row) => row.reason ?? "", text: (row) => row.reason ?? "" },
  ];
}

function changeColumns(page: WebhooksBody): readonly EntityColumn<ChangeRow>[] {
  return [
    {
      id: "change",
      header: "Change",
      hideable: false,
      cell: (row) => CHANGE_LABELS[row.change] ?? row.change,
      text: (row) => CHANGE_LABELS[row.change] ?? row.change,
    },
    { id: "by", header: "By", cell: (row) => personWords(page.people, row.changed_by), text: (row) => personWords(page.people, row.changed_by) },
    { id: "when", header: "When", cell: (row) => at(row.changed_at), text: (row) => at(row.changed_at) },
  ];
}

function Dashboard({ row, onReplay }: { readonly row: SubscriberRow; readonly onReplay: (delivery: DeliveryRow) => void }) {
  return (
    <SectionCard title={DELIVERIES_HEADING}>
      {row.deliveries.length === 0 ? (
        <EmptyState title={NO_DELIVERIES} description={NO_DELIVERIES_DESCRIPTION} />
      ) : (
        <EntityTable
          caption={`Recent deliveries to ${row.subscriber_id}`}
          columns={deliveryColumns()}
          rows={row.deliveries}
          rowId={(one) => `${one.occurred_at}-${one.kind}-${one.state}`}
          rowLabel={(one) => `${one.kind} at ${at(one.occurred_at)}`}
          rowActions={(one) =>
            typeof one.replay === "string" && one.replay !== "" ? (
              <Button
                variant="outline"
                size="sm"
                className="min-h-11 sm:min-h-8"
                aria-label={`${ACT_LABELS.replay}: ${one.kind}`}
                onClick={() => {
                  onReplay(one);
                }}
              >
                {ACT_LABELS.replay}
              </Button>
            ) : null
          }
          exportName={`${row.subscriber_id}-deliveries`}
        />
      )}
    </SectionCard>
  );
}

function Profile({ row, page, onAct }: { readonly row: SubscriberRow; readonly page: WebhooksBody; readonly onAct: (open: Open) => void }) {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title="Where it is told">
        <FactList>
          <Fact label="Address">
            <span className="font-mono text-[12px]">{row.endpoint}</span>
          </Fact>
          <Fact label="Told about">
            <span className="flex flex-wrap gap-1.5">
              {row.kinds.map((one) => (
                <Chip key={one} mono>
                  {one}
                </Chip>
              ))}
            </span>
          </Fact>
          <Fact label="Registered">{`${at(row.created_at)}, by ${personWords(page.people, row.created_by)}`}</Fact>
        </FactList>
      </SectionCard>
      <SectionCard
        title="Signing secret"
        lede="Signs every request, so the receiver can tell it came from this install."
        action={
          row.active ? (
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                onAct("replace");
              }}
            >
              {ACT_LABELS.replace}
            </Button>
          ) : undefined
        }
      >
        <FactList>
          <Fact label="Secret">{secretWord(row)}</Fact>
          {row.secret_written_at === null ? null : <Fact label="Written">{at(row.secret_written_at)}</Fact>}
        </FactList>
        {page.vault === "ready" ? null : (
          <div className="mt-2">
            <Note kind="not-yet">{page.vault_told}</Note>
          </div>
        )}
      </SectionCard>
      <SectionCard
        title="Switch"
        lede={row.active ? "On: it is told whenever one of its kinds happens." : `Off since ${at(row.deactivated_at)}.`}
        action={
          row.active ? (
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 text-crit sm:min-h-8"
              onClick={() => {
                onAct("switch_off");
              }}
            >
              {ACT_LABELS.switchOff}
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                onAct("switch_on");
              }}
            >
              {ACT_LABELS.switchOn}
            </Button>
          )
        }
      >
        <Line>{row.active ? page.switching_off : page.switching_on}</Line>
      </SectionCard>
    </div>
  );
}

function About({ row, page }: { readonly row: SubscriberRow; readonly page: WebhooksBody }) {
  const ids = [...new Set([row.created_by, ...row.changes.map((one) => one.changed_by)])];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title="How delivery works" footer={page.dispatcher === null ? undefined : <Line>{page.dispatcher.told}</Line>}>
        <Line>{page.delivery}</Line>
      </SectionCard>
      <SectionCard title={CHANGES_HEADING}>
        {row.changes.length === 0 ? (
          <Line>{NO_CHANGES}</Line>
        ) : (
          <EntityTable
            caption={`Changes to ${row.subscriber_id}`}
            columns={changeColumns(page)}
            rows={row.changes}
            rowId={(one) => `${one.changed_at}-${one.change}`}
            rowLabel={(one) => CHANGE_LABELS[one.change] ?? one.change}
          />
        )}
      </SectionCard>
      <Advanced>
        <FactList>
          <Fact label="Subscriber id">
            <span className="font-mono text-[12px]">{row.subscriber_id}</span>
          </Fact>
          {ids.map((id) => (
            <Fact key={id} label={personWords(page.people, id)}>
              <span className="font-mono text-[12px]">{id}</span>
            </Fact>
          ))}
        </FactList>
      </Advanced>
    </div>
  );
}

function SubscriberAnswer({ id, tab }: { readonly id: string; readonly tab: string | undefined }) {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const [open, setOpen] = useState<Open>(null);
  const [replaying, setReplaying] = useState<DeliveryRow | null>(null);
  const answer = useResource<unknown>(WEBHOOKS_API_PATH, version);
  const page = useMemo(() => (answer.data === null ? null : readWebhooks(answer.data)), [answer.data]);
  const done = useCallback((sentence: string) => {
    setOpen(null);
    setReplaying(null);
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);
  const act = useCallback((next: Open) => {
    setTold(null);
    setOpen(next);
  }, []);
  const replay = useCallback((delivery: DeliveryRow) => {
    setTold(null);
    setReplaying(delivery);
  }, []);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy || page === null) {
    return answer.busy ? <LoadingState label={LOADING_SUBSCRIBER} /> : null;
  }
  const row = page.subscribers.find((one) => one.subscriber_id === id);
  if (row === undefined) {
    return <PageHeader crumbs={[{ label: WEBHOOKS_HEADING, to: WEBHOOKS_PATH }]} title={NOT_HERE} lede={NOT_HERE_DESCRIPTION} />;
  }
  const view = viewFor(tab);
  const views: DetailView[] = VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: VIEW_LABELS[one], to: viewAddress(id, one), icon: <Icon aria-hidden /> };
  });
  const header = (
    <DetailHeader
      name={row.subscriber_id}
      headingId={`webhook-${row.subscriber_id}`}
      pills={<SubscriberPill active={row.active} />}
      actions={
        row.active ? (
          <>
            <Button
              size="sm"
              variant="outline"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                act("replace");
              }}
            >
              {ACT_LABELS.replace}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="min-h-11 text-crit sm:min-h-8"
              onClick={() => {
                act("switch_off");
              }}
            >
              {ACT_LABELS.switchOff}
            </Button>
          </>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className="min-h-11 sm:min-h-8"
            onClick={() => {
              act("switch_on");
            }}
          >
            {ACT_LABELS.switchOn}
          </Button>
        )
      }
      figures={
        <KpiStrip label={FIGURES_LABEL} count={4}>
          <StatCard label="State" value={row.active ? ON_WORD : OFF_WORD} />
          <StatCard label="Signing secret" value={secretWord(row)} />
          <StatCard label="Last delivered" value={row.last_delivered_at === null ? NEVER_DELIVERED : at(row.last_delivered_at)} />
          <StatCard label="Told about" value={row.kinds.length.toLocaleString("en-GB")} sub={row.kinds.length === 1 ? "kind" : "kinds"} />
        </KpiStrip>
      }
      footnote={told === null || told === "" ? undefined : <Note kind="done">{told}</Note>}
    />
  );
  return (
    <>
      <DetailPage
        crumbs={[{ label: WEBHOOKS_HEADING, to: WEBHOOKS_PATH }, { label: row.subscriber_id }]}
        header={header}
        switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
      >
        {view === "dashboard" ? <Dashboard row={row} onReplay={replay} /> : null}
        {view === "profile" ? <Profile row={row} page={page} onAct={act} /> : null}
        {view === "about" ? <About row={row} page={page} /> : null}
      </DetailPage>
      {open === "replace" ? (
        <ReplaceSecretDrawer
          page={page}
          subscriberId={row.subscriber_id}
          onClose={() => {
            setOpen(null);
          }}
          onDone={done}
        />
      ) : null}
      {open === "switch_off" ? (
        <SwitchOffDialog
          page={page}
          subscriberId={row.subscriber_id}
          onClose={() => {
            setOpen(null);
          }}
          onDone={done}
        />
      ) : null}
      {open === "switch_on" ? (
        <SwitchOnDialog
          page={page}
          subscriberId={row.subscriber_id}
          onClose={() => {
            setOpen(null);
          }}
          onDone={done}
        />
      ) : null}
      {replaying === null ? null : (
        <ReplayDialog
          page={page}
          subscriberId={row.subscriber_id}
          delivery={replaying}
          onClose={() => {
            setReplaying(null);
          }}
          onDone={done}
        />
      )}
    </>
  );
}

export function WebhookDetailPage({ id, tab }: { readonly id: string; readonly tab: string | undefined }) {
  return (
    <div data-slot="webhook-page" className="min-w-0">
      <SubscriberAnswer key={id} id={id} tab={tab} />
    </div>
  );
}
