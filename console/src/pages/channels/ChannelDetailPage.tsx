/**
 * One channel's page on the shared kit, in SCREEN 14's shape: one header shared by three views,
 * Dashboard, Profile and About, each at its own address.
 *
 * **The addresses.** `/channels/{name}` is the Dashboard; `/channels/{name}/profile` and
 * `/channels/{name}/about` are the other two. An address naming anything else opens the Dashboard,
 * so an address typed to probe for a view learns nothing.
 *
 * **Two requests for the frame.** The channel's row is `GET /api/v1/console/channels/{name}`, the
 * list's own row, and what its adapter declares with its health is `GET /api/v1/channels/{name}/
 * health`; a name the reader may not manage and a name that is no channel are one 404, drawn as the
 * API's sentence and not explained.
 *
 * **Switching is confirmed and says what it does.** Switching off says the channel stops receiving
 * and sending at once, and that its vendor's requests are refused from then on, which is
 * M27.15.43's third clause said where a person decides it; switching on says it starts receiving.
 * Both are recorded in the audit ledger by the database, as the dialog says.
 *
 * Task ids: M27.13.1, M27.15.43, M27.16.1, M10.1.4
 */

import { IdCard, Info, LayoutDashboard } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
  DetailHeader,
  DetailPage,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  StatCard,
  UnavailableAction,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { healthApiPath, switchApiPath, type HealthBody } from "../channelsQuery";
import { at } from "../operations/parts";
import { ACT_LABELS, UNAVAILABLE } from "./channelActions";
import { ChannelAbout } from "./ChannelAbout";
import { ChannelDashboard } from "./ChannelDashboard";
import { ChannelProfile } from "./ChannelProfile";
import {
  CHANNELS_ADDRESS,
  SECRET_UNKNOWN_WHY,
  changedByWords,
  channelAddress,
  channelRowApiPath,
  readChannelRow,
  secretWords,
} from "./channelRows";
import { CHANNELS_HEADING, NEVER_ACTIVE } from "./ChannelsPage";
import { HealthPill, StatusPill } from "./pills";

/** The three views, in the owner's order. The first is where the bare address lands. */
export const VIEWS = ["dashboard", "profile", "about"] as const;
export type ChannelView = (typeof VIEWS)[number];

export const VIEW_LABELS: Readonly<Record<ChannelView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

export const VIEWS_LABEL = "Channel views";
export const LOADING_CHANNEL = "Loading this channel.";
export const FIGURES_LABEL = "This channel at a glance";
export const SECRET_LABEL = "Secret";
export const ACTIVE_LABEL = "Last active";
export const CHANGED_LABEL = "Last changed";
export const NEVER_CHANGED = "Never set up";
export const KEEP_LABEL = "Keep it as it is";
export const NOT_SWITCHED = "The channel was not switched";

export const SWITCH_OFF_CONSEQUENCE =
  "It stops receiving and sending at once: every request its vendor posts is refused, and nothing is sent. " +
  "No other channel changes. The switch is recorded in the audit ledger with your name.";
export const SWITCH_ON_CONSEQUENCE =
  "It starts receiving at its events address and replying through its vendor. The switch is recorded in the " +
  "audit ledger with your name.";

const VIEW_ICONS: Readonly<Record<ChannelView, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

/** Where a view of a channel is. The Dashboard is the bare address. */
export function viewAddress(name: string, view: ChannelView): string {
  return view === VIEWS[0] ? channelAddress(name) : `${channelAddress(name)}/${view}`;
}

/** Which view an address opens. Anything unknown opens the Dashboard, silently. */
export function viewFor(tab: string | undefined): ChannelView {
  return tab === "profile" || tab === "about" ? tab : "dashboard";
}

function ChannelAnswer({ name, tab }: { readonly name: string; readonly tab: string | undefined }) {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const answer = useResource<unknown>(channelRowApiPath(name), version);
  const health = useResource<HealthBody>(healthApiPath(name), version);
  const row = useMemo(() => readChannelRow(answer.data), [answer.data]);

  const changed = useCallback((sentence: string) => {
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy || row === null) {
    return answer.busy ? <LoadingState label={LOADING_CHANNEL} /> : null;
  }

  const view = viewFor(tab);
  const on = row.status === "on";
  const verb = on ? ACT_LABELS.switchOff : ACT_LABELS.switchOn;
  const views: DetailView[] = VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: VIEW_LABELS[one], to: viewAddress(name, one), icon: <Icon aria-hidden /> };
  });
  const who = changedByWords(row);

  const flip = () => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(switchApiPath(row.channel), { method: "POST", body: { enabled: !on } });
      setBusy(false);
      setSwitching(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      changed(`${row.label} is switched ${on ? "off" : "on"}.`);
    })();
  };

  const header = (
    <DetailHeader
      name={row.label}
      headingId={`channel-${row.channel}`}
      pills={
        <>
          <StatusPill status={row.status} />
          <HealthPill health={row.health} />
        </>
      }
      subline={row.receives ? undefined : "Not received by this release yet"}
      actions={
        <>
          {row.status === "not_set_up" ? null : (
            <Button
              size="sm"
              variant={on ? "outline" : "default"}
              className="min-h-11 sm:min-h-8"
              disabled={busy}
              onClick={() => {
                setTold(null);
                setFailure(null);
                setSwitching(true);
              }}
            >
              {verb}
            </Button>
          )}
          {row.receives ? (
            <UnavailableAction label={UNAVAILABLE.verify.label} text={UNAVAILABLE.verify.label} reason={UNAVAILABLE.verify.reason} />
          ) : null}
        </>
      }
      figures={
        <KpiStrip label={FIGURES_LABEL} count={3}>
          <StatCard
            label={SECRET_LABEL}
            value={secretWords(row.secret)}
            sub={row.secret === "unknown" ? SECRET_UNKNOWN_WHY : undefined}
          />
          <StatCard label={ACTIVE_LABEL} value={row.last_delivered_at === null ? NEVER_ACTIVE : at(row.last_delivered_at)} />
          <StatCard
            label={CHANGED_LABEL}
            value={row.changed_at === null ? NEVER_CHANGED : at(row.changed_at)}
            sub={who === undefined ? undefined : `by ${who}`}
          />
        </KpiStrip>
      }
      footnote={
        told === null && failure === null ? undefined : (
          <div role="status" className="flex flex-col gap-2">
            {told === null || told === "" ? null : <Note kind="works">{told}</Note>}
            {failure === null ? null : <FailureNotice failure={failure} title={NOT_SWITCHED} />}
          </div>
        )
      }
    />
  );

  return (
    <>
      <DetailPage
        crumbs={[{ label: CHANNELS_HEADING, to: CHANNELS_ADDRESS }, { label: row.label }]}
        header={header}
        switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
      >
        {view === "dashboard" ? <ChannelDashboard row={row} health={health} version={version} onChanged={changed} /> : null}
        {view === "profile" ? <ChannelProfile row={row} onChanged={changed} /> : null}
        {view === "about" ? <ChannelAbout row={row} health={health} version={version} /> : null}
      </DetailPage>
      <ConfirmDialog
        open={switching}
        question={`${verb} ${row.label}?`}
        consequence={on ? SWITCH_OFF_CONSEQUENCE : SWITCH_ON_CONSEQUENCE}
        confirmLabel={verb}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={flip}
        onCancel={() => {
          setSwitching(false);
        }}
      />
    </>
  );
}

export function ChannelDetailPage({ name, tab }: { readonly name: string; readonly tab: string | undefined }) {
  return (
    <div data-slot="channel-page" className="min-w-0">
      <ChannelAnswer key={name} name={name} tab={tab} />
    </div>
  );
}
