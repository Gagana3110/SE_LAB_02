import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { ADMIN, error, fakeServer, PLANNER } from "./testServer";

const CHAIR = { id: 7, code: "P001", name: "Chair", unit: "piece", category: null, active: true };
const DESK = { id: 8, code: "P002", name: "Desk", unit: "piece", category: null, active: true };
const SUMMARY = {
  runId: 5,
  status: "DONE",
  horizon: 2,
  granularity: "MONTH",
  createdAt: "2026-10-31T10:00:00Z",
};
const POINTS = [
  { period: "2026-11-01", forecast: 100, lower80: 90, upper80: 110, lower95: 85, upper95: 115 },
  { period: "2026-12-01", forecast: 120, lower80: 105, upper80: 135, lower95: 98, upper95: 142 },
];
const RUN = {
  runId: 5,
  status: "DONE",
  error: null,
  skipped: [],
  products: [
    { productId: 7, code: "P001", model: "HW", points: POINTS },
    { productId: 8, code: "P002", model: "MA", points: POINTS },
  ],
};
const chartFor = (productId: number, code: string, model: string) => ({
  productId,
  code,
  model,
  points: POINTS,
  history: [{ period: "2026-10-01", actual: 95 }],
});

const base = (user: unknown) => ({
  "GET /auth/me": { body: user },
  "GET /products?active_only=true": { body: [CHAIR, DESK] },
  "GET /forecasts/runs": { body: [SUMMARY] },
  "GET /forecasts/runs/5": { body: RUN },
  "GET /forecasts/runs/5/products/7": { body: chartFor(7, "P001", "HW") },
  "GET /forecasts/runs/5/products/8": { body: chartFor(8, "P002", "MA") },
});

function open() {
  window.history.pushState({}, "", "/forecast");
  render(<App />);
}

beforeEach(() => {
  // The chart library measures its container, which the test browser does not provide.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

describe("forecast page", () => {
  it("shows the latest run with its model and a table of the values", async () => {
    fakeServer(base(PLANNER));
    open();
    expect(await screen.findByRole("cell", { name: "2026-11-01" })).toBeInTheDocument();
    expect(screen.getByText("Holt-Winters")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "115" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Actual and forecast demand for P001/ })).toBeInTheDocument();
  });

  it("switches between products", async () => {
    fakeServer(base(PLANNER));
    open();
    await screen.findByText("Holt-Winters");
    await userEvent.selectOptions(screen.getByLabelText("Product"), "8");
    expect(await screen.findByText("Moving average")).toBeInTheDocument();
    expect(screen.getByText("Forecast values for P002")).toBeInTheDocument();
  });

  it("starts a run for all products, then shows progress until it finishes", async () => {
    let status = "RUNNING";
    const server = fakeServer({
      ...base(PLANNER),
      "GET /forecasts/runs": { body: [] },
      "POST /forecasts/runs": { status: 202, body: { runId: 5, status: "QUEUED" } },
      "GET /forecasts/runs/5": () =>
        status === "RUNNING"
          ? { body: { ...RUN, status, products: [] } }
          : { body: RUN },
    });
    open();
    expect(await screen.findByText("No forecasts have been run yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run forecast" }));
    expect(await screen.findByText(/running in the background/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Forecast running..." })).toBeDisabled();
    expect(server.bodyOf("POST /forecasts/runs")).toEqual({
      productIds: "ALL",
      horizon: 6,
      granularity: "MONTH",
    });
    status = "DONE";
    expect(await screen.findByText("Holt-Winters", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText(/running in the background/)).not.toBeInTheDocument();
  });

  it("sends the chosen product, period and horizon", async () => {
    const server = fakeServer({
      ...base(PLANNER),
      "POST /forecasts/runs": { status: 202, body: { runId: 5, status: "QUEUED" } },
    });
    open();
    await userEvent.selectOptions(await screen.findByLabelText("Products"), "8");
    await userEvent.selectOptions(screen.getByLabelText("Period"), "WEEK");
    const weeks = screen.getByLabelText("Weeks ahead");
    expect(weeks).toHaveValue(12);
    expect(weeks).toHaveAttribute("min", "4");
    await userEvent.click(screen.getByRole("button", { name: "Run forecast" }));
    await waitFor(() =>
      expect(server.bodyOf("POST /forecasts/runs")).toEqual({
        productIds: [8],
        horizon: 12,
        granularity: "WEEK",
      }),
    );
    await userEvent.selectOptions(screen.getByLabelText("Period"), "MONTH");
    expect(screen.getByLabelText("Months ahead")).toHaveValue(6);
  });

  it("shows why a run could not start", async () => {
    fakeServer({
      ...base(PLANNER),
      "POST /forecasts/runs": error(409, "A forecast for these products is already running"),
    });
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Run forecast" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already running");
  });

  it("shows the reason for a failed run", async () => {
    fakeServer({
      ...base(PLANNER),
      "GET /forecasts/runs/5": {
        body: { ...RUN, status: "FAILED", error: "None of the selected products have sales history", products: [] },
      },
    });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("sales history");
  });

  it("lists skipped products with the reason", async () => {
    fakeServer({
      ...base(PLANNER),
      "GET /forecasts/runs/5": {
        body: { ...RUN, skipped: [{ productId: 8, reason: "No sales history" }, { productId: 99, reason: "No sales history" }] },
      },
    });
    open();
    expect(await screen.findByText(/Skipped: P002 Desk \(No sales history\), Product 99/)).toBeInTheDocument();
  });

  it("opens an earlier run", async () => {
    const older = { ...SUMMARY, runId: 4, granularity: "WEEK", horizon: 4 };
    const server = fakeServer({
      ...base(PLANNER),
      "GET /forecasts/runs": { body: [SUMMARY, older] },
      "GET /forecasts/runs/4": { body: { ...RUN, runId: 4, products: [] } },
    });
    open();
    await screen.findByText("Holt-Winters");
    await userEvent.selectOptions(screen.getByLabelText("Forecast run"), "4");
    await waitFor(() =>
      expect(server.calls.some((call) => call.key === "GET /forecasts/runs/4")).toBe(true),
    );
  });

  it("is read-only for other roles", async () => {
    fakeServer(base(ADMIN));
    open();
    expect(await screen.findByText("Holt-Winters")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run forecast" })).not.toBeInTheDocument();
  });

  it("shows an error when a run or chart cannot be loaded", async () => {
    fakeServer({ ...base(PLANNER), "GET /forecasts/runs/5": error(500, "Run problem") });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Run problem");
  });

  it("shows an error when the chart cannot be loaded", async () => {
    fakeServer({ ...base(PLANNER), "GET /forecasts/runs/5/products/7": error(500, "Chart problem") });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Chart problem");
  });
});
