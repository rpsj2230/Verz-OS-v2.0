/**
 * One tool's page, at `/tools/{name}`. The page itself is `tools/ToolDetailPage.tsx`.
 *
 * Task ids: M12.1.1, M27.16.1
 */

import { useParams } from "react-router-dom";
import { ToolDetailPage } from "./tools/ToolDetailPage";

export function Tool() {
  const { name } = useParams();
  return name === undefined ? null : <ToolDetailPage name={name} />;
}
