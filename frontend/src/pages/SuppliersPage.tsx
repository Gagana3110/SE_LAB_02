import { FormEvent, useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { api, Item, messageOf, Supplier } from "../api";
import { useAuth } from "../auth";
import { ErrorMessage, Field } from "../components/Field";
import { useLoad } from "../useLoad";

const EMPTY = {
  code: "",
  name: "",
  lead_time_days: "",
  moq: "",
  unit_price: "",
  monthly_capacity: "",
  reliability_pct: "",
};

const loadPage = () =>
  Promise.all([
    api<Supplier[]>("/suppliers"),
    api<Item[]>("/purchasing/materials-without-supplier"),
  ]);

export function SuppliersPage() {
  const { user } = useAuth();
  const canEdit = user?.role === "administrator";
  const { data, error: loadError, reload } = useLoad(useCallback(loadPage, []));
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");

  const set = (field: keyof typeof EMPTY) => (event: { target: { value: string } }) =>
    setForm({ ...form, [field]: event.target.value });

  const reset = () => {
    setForm(EMPTY);
    setEditing(null);
    setError("");
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await (editing === null
        ? api("/suppliers", { method: "POST", body: form })
        : api(`/suppliers/${editing}`, { method: "PATCH", body: form }));
      reset();
      await reload();
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  const edit = (s: Supplier) => {
    setForm({
      code: s.code,
      name: s.name,
      lead_time_days: String(s.lead_time_days),
      moq: String(s.moq),
      unit_price: String(s.unit_price),
      monthly_capacity: String(s.monthly_capacity),
      reliability_pct: String(s.reliability_pct),
    });
    setEditing(s.id);
    setError("");
  };

  const setActive = async (s: Supplier, active: boolean) => {
    try {
      await api(`/suppliers/${s.id}`, { method: "PATCH", body: { active } });
      setError("");
      await reload();
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  const gaps = data?.[1] ?? [];

  return (
    <section>
      <h1>Suppliers</h1>
      <ErrorMessage text={loadError} />
      {gaps.length > 0 && (
        <p className="message warning" role="status">
          <strong>{gaps.length} raw material(s) have no active supplier:</strong>{" "}
          {gaps.map((material, index) => (
            <span key={material.id}>
              {index > 0 && ", "}
              <Link to={`/materials/${material.id}/suppliers`}>{material.code}</Link>
            </span>
          ))}
        </p>
      )}
      {canEdit && (
        <form className="card form-row" onSubmit={save}>
          <h2>{editing === null ? "Add new" : `Edit ${form.code}`}</h2>
          <ErrorMessage text={error} />
          <div className="fields">
            <Field label="Code" required maxLength={32} value={form.code} onChange={set("code")} />
            <Field label="Name" required maxLength={120} value={form.name} onChange={set("name")} />
            <Field
              label="Lead time (days)"
              type="number"
              required
              min="1"
              value={form.lead_time_days}
              onChange={set("lead_time_days")}
            />
            <Field
              label="Minimum order quantity"
              type="number"
              required
              min="1"
              value={form.moq}
              onChange={set("moq")}
            />
            <Field
              label="Unit price"
              type="number"
              required
              min="0.01"
              step="0.01"
              value={form.unit_price}
              onChange={set("unit_price")}
            />
            <Field
              label="Monthly capacity"
              type="number"
              required
              min="1"
              value={form.monthly_capacity}
              onChange={set("monthly_capacity")}
            />
            <Field
              label="On-time delivery (%)"
              type="number"
              required
              min="0"
              max="100"
              value={form.reliability_pct}
              onChange={set("reliability_pct")}
            />
          </div>
          <div className="actions">
            <button type="submit">{editing === null ? "Add" : "Save changes"}</button>
            {editing !== null && (
              <button type="button" className="secondary" onClick={reset}>
                Cancel
              </button>
            )}
          </div>
        </form>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Code</th>
              <th scope="col">Name</th>
              <th scope="col">Lead time (days)</th>
              <th scope="col">MOQ</th>
              <th scope="col">Unit price</th>
              <th scope="col">Monthly capacity</th>
              <th scope="col">On-time %</th>
              <th scope="col">Status</th>
              {canEdit && <th scope="col">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {data?.[0].map((s) => (
              <tr key={s.id}>
                <td>{s.code}</td>
                <td>{s.name}</td>
                <td>{s.lead_time_days}</td>
                <td>{s.moq}</td>
                <td>{s.unit_price.toFixed(2)}</td>
                <td>{s.monthly_capacity}</td>
                <td>{s.reliability_pct}</td>
                <td>
                  <span className={s.active ? "badge ok" : "badge off"}>
                    {s.active ? "Active" : "Inactive"}
                  </span>
                </td>
                {canEdit && (
                  <td className="row-actions">
                    <button type="button" className="link" onClick={() => edit(s)}>
                      Edit <span className="sr-only">{s.code}</span>
                    </button>
                    <button type="button" className="link" onClick={() => setActive(s, !s.active)}>
                      {s.active ? "Deactivate" : "Activate"}{" "}
                      <span className="sr-only">{s.code}</span>
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {data?.[0].length === 0 && (
              <tr>
                <td colSpan={9}>Nothing added yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
