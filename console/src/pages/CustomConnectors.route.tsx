/**
 * Add an API, at `connectors/new-api`: a hyphen no connector's name can hold, so this address is
 * never one source's page. The page is `connectors/CustomConnectorsPage.tsx`.
 *
 * Task ids: M11.7.8
 */

import type { PageRoutes } from "../routes/page";
import { CustomConnectorsPage } from "./connectors/CustomConnectorsPage";

export const CUSTOM_CONNECTORS_PATH = "/connectors/new-api";

export const routes: PageRoutes = [{ path: "connectors/new-api", element: <CustomConnectorsPage /> }];
