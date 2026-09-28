/**
 * One document's page on the shared kit, in SCREEN 14's shape: one header and its figures, shared by
 * three views at their own addresses. Dashboard is what is recorded about it now, Profile is its
 * record and its text, About is its history.
 *
 * **One request for the page, and each view asks for its own.** `GET /knowledge/items/{id}` fills
 * the header, the figures and the Profile; the reader's own tasks fill the Dashboard's; the About
 * view asks the history route. A 404 is not explained: a document that does not exist and one this
 * reader may not see are one answer (`brain.knowledge.lifecycle.NOT_SEEN`).
 *
 * **The acts are the ones the API offered on this document, and only those.** Verify, a newer
 * version, asking for the whole company and handing over each open a drawer from the header; an act
 * the API did not offer is not drawn, because it is this reader's reach that withholds it and not the
 * product. Archive is drawn inert with its reason, because no route archives a document yet.
 *
 * **The figures are what is recorded**: how many versions the reader may see, when it was last
 * verified (only when the badge may say so), its review date, and the reader's own open tasks on it.
 * No figure is a count of anything hidden.
 *
 * Task ids: M27.15.40, M27.16.1, M7.4.4, M7.4.5, M7.4.6, M7.7.2
 */

import { ArrowRightLeft, CheckCircle2, ChevronDown, FilePlus2, Globe2, IdCard, Info, LayoutDashboard } from "lucide-react";
import { useMemo, useState } from "react";
import { useResource } from "../../api/useResource";
import {
  DetailHeader,
  DetailPage,
  Drawer,
  FailureState,
  KpiStrip,
  LoadingState,
  StatCard,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { itemPath, TASKS_API_PATH } from "../knowledgeLifecycleQuery";
import { HandOverForm, NewVersionForm, ProposeForm, VerifyForm } from "./actForms";
import { KnowledgeAbout } from "./KnowledgeAbout";
import { KnowledgeDashboard } from "./KnowledgeDashboard";
import { UNAVAILABLE, type DocumentAct } from "./knowledgeActions";
import {
  dayWords,
  KNOWLEDGE_HEADING,
  LIBRARY_ADDRESS,
  levelWords,
  readDocumentPage,
  readTasks,
  viewAddress,
  viewFor,
  VIEWS,
  type DocumentViewKey,
} from "./knowledgeDocuments";
import { KnowledgeProfile } from "./KnowledgeProfile";
import { DuePill, StatePill } from "./parts";

export const VIEW_LABELS: Readonly<Record<DocumentViewKey, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

const VIEW_ICONS: Readonly<Record<DocumentViewKey, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

export const VIEWS_LABEL = "Document views";
export const LOADING_DOCUMENT = "Loading this document.";
export const FIGURES_LABEL = "This document at a glance";
export const ACTS_LABEL = "More actions";

/** The acts a drawer opens, with the words each drawer is headed by. */
export const ACTS: Readonly<Record<DocumentAct, { readonly label: string; readonly description: string }>> = Object.freeze({
  verify: { label: "Verify", description: "Say it is right today, and when it must be looked at again." },
  version: { label: "Add a newer version", description: "Replace the text answers are drawn from. This version stays in the history." },
  propose: {
    label: "Ask for the whole company",
    description: "A card waits on the Approvals screen for somebody else to approve.",
  },
  handOver: { label: "Hand to another steward", description: "Name who answers for it being right from now on." },
});
type Act = DocumentAct;

/** A figure for when it was last verified: the day when the badge may say it, else what it can say. */
export function lastVerifiedWords(verification: string, verifiedAt: string | undefined): string {
  const day = dayWords(verifiedAt);
  if (day !== undefined) {
    return day;
  }
  switch (verification) {
    case "verified":
      return "Verified";
    case "due":
      return "Due again";
    case "superseded":
      return "Replaced";
    default:
      return "Never";
  }
}

function DocumentAnswer({ itemId, view }: { readonly itemId: string; readonly view: DocumentViewKey }) {
  const [version, setVersion] = useState(0);
  const changed = () => {
    setVersion((was) => was + 1);
  };
  const answer = useResource<unknown>(itemPath(itemId), version);
  const page = useMemo(() => readDocumentPage(answer.data), [answer.data]);
  const tasks = useResource<unknown>(TASKS_API_PATH, version);
  const mine = useMemo(() => (tasks.failure === null ? readTasks(tasks.data).filter((one) => one.itemId === itemId) : []), [tasks, itemId]);
  const [acting, setActing] = useState<Act | null>(null);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy) {
    return <LoadingState label={LOADING_DOCUMENT} />;
  }
  if (page === null) {
    return null;
  }
  const { document, versions, offered } = page;
  const acts = (
    [
      ["verify", offered.verify],
      ["version", offered.newVersion],
      ["propose", offered.propose],
      ["handOver", offered.handOver],
    ] as const
  )
    .filter(([, on]) => on)
    .map(([act]) => act);
  const done = () => {
    setActing(null);
    changed();
  };
  const views: DetailView[] = VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: VIEW_LABELS[one], to: viewAddress(itemId, one), icon: <Icon aria-hidden /> };
  });
  const subline = [
    document.kindLabel,
    levelWords(document.level),
    document.department,
    document.stewardName === undefined ? undefined : `steward ${document.stewardName}`,
  ]
    .filter((one): one is string => one !== undefined)
    .join(" · ");
  const icons: Readonly<Record<Act, typeof CheckCircle2>> = {
    verify: CheckCircle2,
    version: FilePlus2,
    propose: Globe2,
    handOver: ArrowRightLeft,
  };

  const header = (
    <DetailHeader
      name={document.title}
      headingId={`document-${itemId}`}
      pills={
        <>
          <StatePill state={document.state} />
          {document.due ? <DuePill /> : null}
        </>
      }
      subline={subline === "" ? undefined : subline}
      actions={
        <>
          {acts.includes("verify") ? (
            <Button
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                setActing("verify");
              }}
            >
              <CheckCircle2 aria-hidden /> {ACTS.verify.label}
            </Button>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8">
                {ACTS_LABEL} <ChevronDown aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              {acts
                .filter((act) => act !== "verify")
                .map((act) => {
                  const Icon = icons[act];
                  return (
                    <DropdownMenuItem
                      key={act}
                      onSelect={() => {
                        setActing(act);
                      }}
                    >
                      <Icon aria-hidden /> {ACTS[act].label}
                    </DropdownMenuItem>
                  );
                })}
              {acts.some((act) => act !== "verify") ? <DropdownMenuSeparator /> : null}
              <DropdownMenuLabel className="text-[11px] font-normal text-dim">Coming soon</DropdownMenuLabel>
              <DropdownMenuItem disabled className="flex-col items-start gap-0.5">
                <span>Archive</span>
                <span className="text-[11px] leading-snug text-dim">{UNAVAILABLE.archive.reason}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </>
      }
      figures={
        <KpiStrip label={FIGURES_LABEL} count={tasks.failure === null && !tasks.busy ? 4 : 3}>
          <StatCard label="Versions" value={String(versions.length)} sub={versions.length === 1 ? "this one only" : "you can see"} />
          <StatCard label="Last verified" value={lastVerifiedWords(document.verification, document.verifiedAt)} />
          <StatCard label="Review by" value={dayWords(document.reviewBy) ?? "Not set"} sub={document.due ? "due now" : undefined} />
          {tasks.failure === null && !tasks.busy ? (
            <StatCard label="Your open tasks" value={String(mine.length)} sub="on this document" />
          ) : null}
        </KpiStrip>
      }
    />
  );

  const shown = acting ?? "verify";
  return (
    <DetailPage
      crumbs={[{ label: KNOWLEDGE_HEADING, to: LIBRARY_ADDRESS }, { label: document.title }]}
      header={header}
      switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
    >
      {view === "dashboard" ? (
        <KnowledgeDashboard
          page={page}
          tasks={mine}
          onChanged={changed}
          onAct={(act) => {
            setActing(act);
          }}
          offers={acts}
        />
      ) : null}
      {view === "profile" ? <KnowledgeProfile page={page} /> : null}
      {view === "about" ? <KnowledgeAbout itemId={itemId} versions={versions} version={version} /> : null}
      <Drawer
        open={acting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setActing(null);
          }
        }}
        title={ACTS[shown].label}
        description={ACTS[shown].description}
      >
        {shown === "verify" ? <VerifyForm itemId={itemId} onDone={done} /> : null}
        {shown === "version" ? <NewVersionForm itemId={itemId} title={document.title} onDone={done} /> : null}
        {shown === "propose" ? <ProposeForm itemId={itemId} waits={page.promotionWaits} onDone={done} /> : null}
        {shown === "handOver" ? <HandOverForm itemId={itemId} title={document.title} onDone={done} /> : null}
      </Drawer>
    </DetailPage>
  );
}

export function KnowledgeDetailPage({ itemId, view }: { readonly itemId: string; readonly view: string | undefined }) {
  return (
    <div data-slot="document-page" className="min-w-0">
      <DocumentAnswer key={itemId} itemId={itemId} view={viewFor(view)} />
    </div>
  );
}

