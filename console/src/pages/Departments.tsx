/**
 * Departments and teams, at the addresses the route table and the menu use: `/departments` is the
 * list and `/departments/{slug}` and `/departments/{slug}/{view}` are one department's page. Both
 * are built on the shared page kit in `departments/`; this module keeps the name the route file loads.
 *
 * Task ids: M27.11.1, M27.16.1
 */

import { useParams } from "react-router-dom";
import { DepartmentDetailPage } from "./departments/DepartmentDetailPage";
import { DepartmentsPage } from "./departments/DepartmentsPage";
import { departmentViewNamed } from "./departments/departmentsQuery";

export { DEPARTMENTS_HEADING, DEPARTMENTS_LEDE, NO_DEPARTMENTS } from "./departments/DepartmentsPage";

export function Departments() {
  const { slug, view } = useParams();
  if (slug === undefined) {
    return <DepartmentsPage />;
  }
  return <DepartmentDetailPage key={slug} slug={slug} view={departmentViewNamed(view)} />;
}
