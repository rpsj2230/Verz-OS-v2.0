/**
 * Channels, E1 of Channels and notifications: the list of every chat channel the reader manages,
 * and one channel's page with its Dashboard, Profile and About views. No registry key: the pages
 * cite `brain.console.channel_health` instead. A person's own chats are a card in My workspace,
 * `components/MyChannels.tsx`, and need no route of their own.
 *
 * Task ids: M27.13.1, M27.16.1, M10.3.4, M10.1.2, M10.1.3, M10.1.4
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";
import { Channels } from "./Channels";

const Channel = lazy(async () => ({ default: (await import("./Channel")).Channel }));

export const routes: PageRoutes = [
  { path: "channels", element: <Channels /> },
  { path: "channels/:name", element: <Channel /> },
  { path: "channels/:name/:view", element: <Channel /> },
];
