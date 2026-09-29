/**
 * One automation's page on the shared kit, in SCREEN 14's shape: one header shared by three views,
 * Dashboard, Profile and About, each at its own address.
 *
 * **The addresses.** `/automations/{id}` is the Dashboard; `/automations/{id}/profile` and
 * `/automations/{id}/about` are the other two. An address naming anything else opens the Dashboard.
 *
 * **Every change the API offers this reader works, and each is confirmed.** Pause, resume, change
 * the schedule, remove and adopt are drawn only when the API said this reader may make them
 * (`may_*`), and each sends the confirmation the page was sent (`AutomationActs.tsx`). Bringing back
 * a removed automation has no route, so on a removed automation it is `kit/UnavailableAction` with
 * `automationActions.ts`' sentence. The page decides nothing: the API decides again on arrival.
 *
 * **A 404 is not explained.** An automation that does not exist, one on an agent the reader may not
 * see and one the reader may not see are one answer.
 *
 * Task ids: M27.12.3, M27.15.37, M39.6.1.4, M39.6.1.5, M27.16.1, M27.10.2
 */

import { IdCard, Info, LayoutDashboard, Pause, Play, Trash2, UserPlus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  DetailHeader,
  DetailPage,
  FailureState,
  LoadingState,
  Note,
  UnavailableAction,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { ACT_LABELS, UNAVAILABLE } from "./automationActions";
import { ChangeDialog, ScheduleDrawer } from "./AutomationActs";
import { AutomationAbout } from "./AutomationAbout";
import { AutomationDashboard } from "./AutomationDashboard";
import { AutomationProfile } from "./AutomationProfile";
import {
  AUTOMATIONS_ADDRESS,
  automationAddress,
  automationApiPath,
  readAutomationDetail,
  type AutomationDetail,
  type ChangeAct,
} from "./automationsQuery";
import { AUTOMATIONS_HEADING } from "./AutomationsPage";
import { StatePill } from "./pills";

/** The three views, in the owner's order. The first is where the bare address lands. */
export const VIEWS = ["dashboard", "profile", "about"] as const;
export type AutomationView = (typeof VIEWS)[number];

export const VIEW_LABELS: Readonly<Record<AutomationView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

export const VIEWS_LABEL = "Automation views";
export const LOADING_AUTOMATION = "Loading this automation.";

const VIEW_ICONS: Readonly<Record<AutomationView, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

/** Where a view of an automation is. The Dashboard is the bare address. */
export function viewAddress(id: string, view: AutomationView): string {
  return view === VIEWS[0] ? automationAddress(id) : `${automationAddress(id)}/${view}`;
}

/** Which view an address opens. Anything unknown opens the Dashboard, silently. */
export function viewFor(tab: string | undefined): AutomationView {
  return tab === "profile" || tab === "about" ? tab : "dashboard";
}

const ACT_ICONS = { pause: Pause, resume: Play, adopt: UserPlus } as const;

function Acts({
  detail,
  onAct,
}: {
  readonly detail: AutomationDetail;
  readonly onAct: (act: ChangeAct) => void;
}) {
  const buttons = (["adopt", "resume", "pause"] as const).filter((one) => detail.may[one]);
  return (
    <>
      {buttons.map((one) => {
        const Icon = ACT_ICONS[one];
        return (
          <Button
            key={one}
            size="sm"
            variant={one === "pause" ? "outline" : "default"}
            className="min-h-11 sm:min-h-8"
            onClick={() => {
              onAct(one);
            }}
          >
            <Icon aria-hidden />
            {ACT_LABELS[one]}
          </Button>
        );
      })}
      {detail.may.reschedule ? (
        <Button
          size="sm"
          variant="outline"
          className="min-h-11 sm:min-h-8"
          onClick={() => {
            onAct("reschedule");
          }}
        >
          {ACT_LABELS.reschedule}
        </Button>
      ) : null}
      {detail.may.remove ? (
        <Button
          size="sm"
          variant="outline"
          className="min-h-11 text-crit sm:min-h-8"
          onClick={() => {
            onAct("remove");
          }}
        >
          <Trash2 aria-hidden />
          {ACT_LABELS.remove}
        </Button>
      ) : null}
      {detail.row.state === "removed" ? (
        <UnavailableAction label={ACT_LABELS.reinstate} text={ACT_LABELS.reinstate} reason={UNAVAILABLE.reinstate.reason} />
      ) : null}
    </>
  );
}

function AutomationAnswer({ id, tab }: { readonly id: string; readonly tab: string | undefined }) {
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState<ChangeAct | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<unknown>(automationApiPath(id), version);
  const detail = useMemo(() => readAutomationDetail(answer.data), [answer.data]);

  const done = useCallback((sentence: string) => {
    setOpen(null);
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);
  const close = useCallback(() => {
    setOpen(null);
  }, []);
  const act = useCallback((next: ChangeAct) => {
    setTold(null);
    setOpen(next);
  }, []);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy || detail === null) {
    return answer.busy ? <LoadingState label={LOADING_AUTOMATION} /> : null;
  }
  const { row } = detail;
  const view = viewFor(tab);
  const views: DetailView[] = VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: VIEW_LABELS[one], to: viewAddress(id, one), icon: <Icon aria-hidden /> };
  });
  const subline = [row.agentName, row.ownerName === "" ? null : `runs as ${row.ownerName}`, row.schedule ?? null]
    .filter((one): one is string => one !== null && one !== "")
    .join(" · ");

  const header = (
    <DetailHeader
      name={row.name}
      headingId={`automation-${row.id}`}
      pills={<StatePill state={row.state} />}
      subline={subline}
      actions={<Acts detail={detail} onAct={act} />}
      footnote={
        told === null && detail.stoppedBecause === undefined ? undefined : (
          <div className="flex flex-col gap-1.5">
            {told === null ? null : (
              <div role="status">
                <Note kind="done">{told}</Note>
              </div>
            )}
            {detail.stoppedBecause === undefined ? null : <Note>{detail.stoppedBecause}</Note>}
          </div>
        )
      }
    />
  );

  return (
    <>
      <DetailPage
        crumbs={[{ label: AUTOMATIONS_HEADING, to: AUTOMATIONS_ADDRESS }, { label: row.name }]}
        header={header}
        switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
        beside={
          <Link to={`/agents/${encodeURIComponent(row.agentId)}/automations`} className="text-[12.5px] text-acc-text underline-offset-4 hover:underline">
            Open {row.agentName}
          </Link>
        }
      >
        {view === "dashboard" ? <AutomationDashboard detail={detail} /> : null}
        {view === "profile" ? <AutomationProfile detail={detail} /> : null}
        {view === "about" ? <AutomationAbout detail={detail} /> : null}
      </DetailPage>
      {open === "reschedule" ? <ScheduleDrawer detail={detail} onClose={close} onDone={done} /> : null}
      {open !== null && open !== "reschedule" ? (
        <ChangeDialog detail={detail} act={open} onClose={close} onDone={done} />
      ) : null}
    </>
  );
}

export function AutomationDetailPage({ id, tab }: { readonly id: string; readonly tab: string | undefined }) {
  return (
    <div data-slot="automation-page" className="min-w-0">
      <AutomationAnswer key={id} id={id} tab={tab} />
    </div>
  );
}
