/**
 * The API's answer about which console a reader is given, as the tests that mount the shell send it.
 *
 * The shell asks `GET /api/v1/console/navigation` before it draws anything but the reader's own
 * work, so every test that looks at the menu has to answer that request. Written once, here, in
 * the shape `brain.navigation_routes.NavigationView` sends, so a test cannot quietly hold a
 * different idea of the body from the one `tests/department-console.test.tsx` compares with the
 * Python model.
 *
 * Task ids: none
 */

/** Where the shell asks, as the stand-in API sees the path. */
export const NAVIGATION_ADDRESS = "/api/v1/console/navigation";

/** The company console: its menu is the shell's own, so the answer carries none. */
export const COMPANY_CONSOLE = Object.freeze({ console: "company", departments: [], sections: [] });

/** SCREEN 2's menu for one department, as `brain.console.department_console` declares it. */
export function departmentConsole(department = "maintenance"): Record<string, unknown> {
  return {
    console: "department",
    departments: [department],
    sections: [
      {
        heading: "Operate",
        entries: [
          { key: "overview", label: "Department", to: "/department" },
          { key: "runs", label: "Live runs", to: "/runs" },
          { key: "connectors", label: "Connectors", to: "/connectors" },
        ],
      },
      {
        heading: "Govern",
        entries: [
          { key: "people", label: "People and grants", to: "/people" },
          { key: "agents", label: "Agents and leashes", to: "/agents" },
          { key: "library", label: "Knowledge", to: "/library" },
          { key: "skills", label: "Skills", to: "/skills" },
          { key: "learning", label: "Learning", to: "/learning" },
        ],
      },
      {
        heading: "Report",
        entries: [
          { key: "questions", label: "Gaps", to: "/questions" },
          { key: "usage", label: "Usage", to: "/usage" },
        ],
      },
    ],
  };
}

/** The navigation request answered with `body`, or null for any other request. */
export function answerNavigation(url: string, body: unknown = COMPANY_CONSOLE): Response | null {
  if (new URL(url, "https://console.test").pathname !== NAVIGATION_ADDRESS) {
    return null;
  }
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}
