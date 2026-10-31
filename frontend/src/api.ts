export type Role =
  | "administrator"
  | "demand_planner"
  | "inventory_manager"
  | "procurement_manager";

export interface User {
  id: number;
  email: string;
  role: Role;
}

export interface Item {
  id: number;
  code: string;
  name: string;
  unit: string;
  category: string | null;
  active: boolean;
}

export interface BomLine {
  material: Item;
  qty_per_unit: number;
}

export interface Supplier {
  id: number;
  code: string;
  name: string;
  lead_time_days: number;
  moq: number;
  unit_price: number;
  monthly_capacity: number;
  reliability_pct: number;
  active: boolean;
}

export interface SupplierLink {
  supplier: Supplier;
  preferred: boolean;
}

export interface ImportResult {
  id: number;
  filename: string;
  imported: number;
  updated: number;
  rejected: number;
  errors: { row: number; field: string; message: string }[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export const SESSION_EXPIRED_EVENT = "dfs:session-expired";

interface ApiOptions {
  method?: string;
  body?: unknown;
  file?: File;
}

async function readError(response: Response): Promise<string> {
  try {
    const { error } = await response.json();
    const details = (error.details ?? []).map(
      (d: { field: string; message: string }) => `${d.field}: ${d.message}`,
    );
    return [error.message, ...details].join(" - ");
  } catch {
    return "Something went wrong. Please try again.";
  }
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const init: RequestInit = { method: options.method ?? "GET" };
  if (options.file) {
    const form = new FormData();
    form.append("file", options.file);
    init.body = form;
  } else if (options.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("The server cannot be reached. Please try again.", 0);
  }
  if (response.status === 401 && path !== "/auth/login" && path !== "/auth/me") {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}
