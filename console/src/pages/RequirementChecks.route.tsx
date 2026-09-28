/**
 * Requirement checks: the requirements register by area and what a person saw on this install. Not
 * in the menu: it proves the product's own build rather than administering a company, so it is
 * reached by its address. See `brain.console.department_console.COMPANY_NAVIGATION`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { RequirementChecks } from "./RequirementChecks";

export const routes: PageRoutes = [
  { path: "requirement-checks", element: <RequirementChecks /> },
];
