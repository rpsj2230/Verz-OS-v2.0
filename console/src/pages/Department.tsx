/**
 * Department, rebuilt on the page kit in `department/DepartmentHomePage.tsx`. This module keeps the
 * name the route file imports and reads the view out of the address.
 *
 * Task ids: M27.7.29, M27.16.1
 */

import { useParams } from "react-router-dom";
import { homeViewNamed } from "./department/departmentHome";
import { DepartmentHomePage } from "./department/DepartmentHomePage";

export function Department() {
  const { view } = useParams();
  return <DepartmentHomePage view={homeViewNamed(view)} />;
}
