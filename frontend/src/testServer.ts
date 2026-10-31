import { vi } from "vitest";

type Reply = { status?: number; body?: unknown } | ((init: RequestInit) => { status?: number; body?: unknown });

/** A stand-in for the backend. Keys look like "POST /auth/login"; unknown requests return 404. */
export function fakeServer(routes: Record<string, Reply>) {
  const calls: { key: string; init: RequestInit }[] = [];
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const key = `${init.method ?? "GET"} ${url.replace(/^\/api/, "")}`;
    calls.push({ key, init });
    const route = routes[key];
    const reply = typeof route === "function" ? route(init) : route;
    if (!reply) {
      return new Response(JSON.stringify({ error: { code: 404, message: "Not found" } }), {
        status: 404,
      });
    }
    const status = reply.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), { status });
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    calls,
    bodyOf: (key: string) =>
      JSON.parse(calls.filter((call) => call.key === key).at(-1)?.init.body as string),
  };
}

export const error = (status: number, message: string, details?: unknown) => ({
  status,
  body: { error: { code: status, message, details }, requestId: "test" },
});

export const ADMIN = { id: 1, email: "admin@dfs-demo.com", role: "administrator" };
export const PLANNER = { id: 2, email: "planner@dfs-demo.com", role: "demand_planner" };
export const INVENTORY = { id: 3, email: "stock@dfs-demo.com", role: "inventory_manager" };
export const BUYER = { id: 4, email: "buyer@dfs-demo.com", role: "procurement_manager" };
