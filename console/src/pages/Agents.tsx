/**
 * The Agents list's address in the route table. The page itself is `agents/AgentsPage.tsx`, built
 * on the shared page kit; this module keeps the name `App.tsx` and `Department.tsx` import, so the
 * route table did not have to change for the rebuild.
 *
 * Task ids: M39.1.2.5, M27.10.2
 */

export {
  AgentsPage as Agents,
  agentAddress,
  NO_AGENTS,
  ROSTER_HEADING,
  ROSTER_LEDE,
  ROSTER_LIST_LABEL,
} from "./agents/AgentsPage";
