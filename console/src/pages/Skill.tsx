/**
 * One skill's page, at `/skills/{name}` and `/skills/{name}/{view}`. The page itself is
 * `skills/SkillDetailPage.tsx`, built on the shared page kit; this module reads the address.
 *
 * Task ids: M27.16.1
 */

import { useParams } from "react-router-dom";
import { SkillDetailPage } from "./skills/SkillDetailPage";

export function Skill() {
  const { name, view } = useParams();
  return name === undefined ? null : <SkillDetailPage name={name} view={view} />;
}
