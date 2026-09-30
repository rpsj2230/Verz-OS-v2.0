/**
 * The shared page kit: the parts every module page of the admin console is built from.
 *
 * A module page is a `ListPage` over the list contract and a `DetailPage` with views, both built from
 * the parts below, so a page added next month looks and behaves like Agents without copying it.
 * `pages/agents/` is the worked example: `AgentsPage.tsx` for a list, `AgentDetailPage.tsx` for one
 * entity, `agentStats.ts` for a module's figures and `agentActions.ts` for which acts are live.
 *
 * Task ids: M27.10.2
 */

export { ConfirmDialog, type ConfirmDialogProps } from "./ConfirmDialog";
export {
  BACK,
  ConnectFlow,
  COPIED_TEXT,
  FLAGGED,
  FlowDialog,
  indexOf,
  NEXT,
  NOT_COPIED_TEXT,
  SHOW_TEXT,
  StepPicture,
  stepOf,
  type FlowStep,
} from "./ConnectFlow";
export { copied } from "./copyText";
export { DetailHeader, DetailPage, ViewSwitch, type DetailView } from "./DetailPage";
export { Drawer } from "./Drawer";
export { EntityTable, saveCsv, selectedWords, toCsv, type EntityColumn } from "./EntityTable";
export { FIGURES_FAILED, FIGURES_LOADING, KpiStrip, NOT_RECORDED, StatCard, StatsStrip } from "./KpiStrip";
export { ListPage, type ListPageProps } from "./ListPage";
export { ListToolbar, RESET_LABEL } from "./ListToolbar";
export { Crumbs, PageHeader, type Crumb } from "./PageHeader";
export {
  Advanced,
  Chip,
  Fact,
  FactList,
  initialsOf,
  Note,
  NOTE_LEADS,
  NotOffered,
  SectionCard,
  UNAVAILABLE_MARK,
  UnavailableAction,
  type NoteKind,
} from "./parts";
export { EmptyState, FailureState, LoadingState } from "./states";
export { forgetFlow, recallFlow, rememberFlow } from "./flowMemory";
export { sketchMarks, sketchWords, StepSketch, type SketchView } from "./StepSketch";
