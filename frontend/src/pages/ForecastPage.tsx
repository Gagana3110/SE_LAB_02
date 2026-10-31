import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, Item, messageOf } from "../api";
import { useAuth } from "../auth";
import { ErrorMessage, Field } from "../components/Field";
import { useLoad } from "../useLoad";

interface RunSummary {
  runId: number;
  status: string;
  horizon: number;
  granularity: string;
  createdAt: string;
}

interface Point {
  period: string;
  forecast: number;
  lower80: number;
  upper80: number;
  lower95: number;
  upper95: number;
}

interface ProductForecast {
  productId: number;
  code: string;
  model: string;
  points: Point[];
}

interface RunDetail {
  runId: number;
  status: string;
  error: string | null;
  skipped: { productId: number; reason: string }[];
  products: ProductForecast[];
}

interface Chart extends ProductForecast {
  history: { period: string; actual: number }[];
}

export const POLL_MS = 2000;
const MODEL_NAMES: Record<string, string> = { MA: "Moving average", HW: "Holt-Winters" };
const LIMITS = { MONTH: { min: 1, max: 12 }, WEEK: { min: 4, max: 52 } };
const isActive = (status?: string) => status === "QUEUED" || status === "RUNNING";

function chartRows(chart: Chart) {
  const rows: Record<string, unknown>[] = chart.history.map((h) => ({
    period: h.period,
    actual: h.actual,
  }));
  chart.points.forEach((p) =>
    rows.push({
      period: p.period,
      forecast: p.forecast,
      range80: [p.lower80, p.upper80],
      range95: [p.lower95, p.upper95],
    }),
  );
  return rows;
}

export function ForecastPage() {
  const { user } = useAuth();
  const canRun = user?.role === "demand_planner";
  const loadPage = useCallback(
    () =>
      Promise.all([
        api<Item[]>("/products?active_only=true"),
        api<RunSummary[]>("/forecasts/runs"),
      ]),
    [],
  );
  const { data, error: loadError, reload } = useLoad(loadPage);
  const products = data?.[0] ?? [];
  const runs = data?.[1] ?? [];

  const [productId, setProductId] = useState("ALL");
  const [granularity, setGranularity] = useState<"MONTH" | "WEEK">("MONTH");
  const [horizon, setHorizon] = useState("6");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [shownProduct, setShownProduct] = useState<number | null>(null);
  const [chart, setChart] = useState<Chart | null>(null);

  useEffect(() => {
    if (runId === null && runs.length > 0) setRunId(runs[0].runId);
  }, [runId, runs]);

  useEffect(() => {
    if (runId === null) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const detail = await api<RunDetail>(`/forecasts/runs/${runId}`);
        if (stopped) return;
        setRun(detail);
        setError("");
        if (isActive(detail.status)) timer = setTimeout(check, POLL_MS);
        else void reload();
      } catch (reason) {
        if (!stopped) setError(messageOf(reason));
      }
    };
    setRun(null);
    setShownProduct(null);
    setChart(null);
    void check();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [runId, reload]);

  const firstProduct = run?.products[0]?.productId ?? null;
  const selected = shownProduct ?? firstProduct;

  useEffect(() => {
    if (runId === null || selected === null) return;
    let stopped = false;
    api<Chart>(`/forecasts/runs/${runId}/products/${selected}`)
      .then((value) => {
        if (!stopped) setChart(value);
      })
      .catch((reason) => {
        if (!stopped) setError(messageOf(reason));
      });
    return () => {
      stopped = true;
    };
  }, [runId, selected]);

  const start = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = {
        productIds: productId === "ALL" ? "ALL" : [Number(productId)],
        horizon: Number(horizon),
        granularity,
      };
      const accepted = await api<{ runId: number }>("/forecasts/runs", { method: "POST", body });
      setRunId(accepted.runId);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  };

  const changeGranularity = (value: "MONTH" | "WEEK") => {
    setGranularity(value);
    setHorizon(value === "MONTH" ? "6" : "12");
  };

  const productLabel = (id: number) => {
    const product = products.find((item) => item.id === id);
    return product ? `${product.code} ${product.name}` : `Product ${id}`;
  };

  return (
    <section>
      <h1>Demand forecast</h1>
      <ErrorMessage text={loadError || error} />

      {canRun && (
        <form className="card form-row" onSubmit={start}>
          <h2>Run a new forecast</h2>
          <div className="fields">
            <label className="field">
              <span>Products</span>
              <select value={productId} onChange={(e) => setProductId(e.target.value)}>
                <option value="ALL">All active products</option>
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.code} {product.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Period</span>
              <select
                value={granularity}
                onChange={(e) => changeGranularity(e.target.value as "MONTH" | "WEEK")}
              >
                <option value="MONTH">Monthly</option>
                <option value="WEEK">Weekly</option>
              </select>
            </label>
            <Field
              label={granularity === "MONTH" ? "Months ahead" : "Weeks ahead"}
              type="number"
              required
              {...LIMITS[granularity]}
              value={horizon}
              onChange={(e) => setHorizon(e.target.value)}
            />
          </div>
          <div className="actions">
            <button type="submit" disabled={busy || isActive(run?.status)}>
              {isActive(run?.status) ? "Forecast running..." : "Run forecast"}
            </button>
          </div>
        </form>
      )}

      {runs.length > 0 && (
        <label className="field narrow">
          <span>Forecast run</span>
          <select
            value={runId ?? ""}
            onChange={(e) => setRunId(Number(e.target.value))}
          >
            {runs.map((item) => (
              <option key={item.runId} value={item.runId}>
                #{item.runId}: {new Date(item.createdAt).toLocaleString()} ({item.status},{" "}
                {item.horizon} {item.granularity === "MONTH" ? "months" : "weeks"})
              </option>
            ))}
          </select>
        </label>
      )}

      {data && runs.length === 0 && runId === null && (
        <p className="hint">No forecasts have been run yet.</p>
      )}

      {isActive(run?.status) && (
        <p className="message info" role="status">
          The forecast is running in the background. You can keep working; this page updates by
          itself.
        </p>
      )}
      {run?.status === "FAILED" && <ErrorMessage text={run.error ?? "The forecast failed."} />}
      {run && run.skipped.length > 0 && (
        <p className="message warning" role="status">
          Skipped:{" "}
          {run.skipped.map((s) => `${productLabel(s.productId)} (${s.reason})`).join(", ")}
        </p>
      )}

      {run && run.products.length > 0 && (
        <label className="field narrow">
          <span>Product</span>
          <select
            value={selected ?? ""}
            onChange={(e) => {
              setChart(null);
              setShownProduct(Number(e.target.value));
            }}
          >
            {run.products.map((product) => (
              <option key={product.productId} value={product.productId}>
                {productLabel(product.productId)}
              </option>
            ))}
          </select>
        </label>
      )}

      {chart && (
        <>
          <div className="card">
            <h2>
              {productLabel(chart.productId)}{" "}
              <span className="badge ok">{MODEL_NAMES[chart.model] ?? chart.model}</span>
            </h2>
            <div className="chart" role="img" aria-label={`Actual and forecast demand for ${chart.code}. The same values are in the table below.`}>
              <ResponsiveContainer width="100%" height={360}>
                <ComposedChart data={chartRows(chart)}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#d3dae1" />
                  <XAxis dataKey="period" minTickGap={32} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Area
                    dataKey="range95"
                    name="95% range"
                    stroke="none"
                    fill="#1f5fa8"
                    fillOpacity={0.12}
                    isAnimationActive={false}
                  />
                  <Area
                    dataKey="range80"
                    name="80% range"
                    stroke="none"
                    fill="#1f5fa8"
                    fillOpacity={0.22}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="actual"
                    name="Actual"
                    stroke="#1c2733"
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="forecast"
                    name="Forecast"
                    stroke="#b5491a"
                    strokeWidth={2}
                    strokeDasharray="6 3"
                    dot={{ r: 3 }}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <caption>Forecast values for {chart.code}</caption>
              <thead>
                <tr>
                  <th scope="col">Period</th>
                  <th scope="col">Forecast</th>
                  <th scope="col">80% low</th>
                  <th scope="col">80% high</th>
                  <th scope="col">95% low</th>
                  <th scope="col">95% high</th>
                </tr>
              </thead>
              <tbody>
                {chart.points.map((point) => (
                  <tr key={point.period}>
                    <td>{point.period}</td>
                    <td>{point.forecast}</td>
                    <td>{point.lower80}</td>
                    <td>{point.upper80}</td>
                    <td>{point.lower95}</td>
                    <td>{point.upper95}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
