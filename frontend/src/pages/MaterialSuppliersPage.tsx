import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Item, messageOf, Supplier, SupplierLink } from "../api";
import { useAuth } from "../auth";
import { ErrorMessage, SuccessMessage } from "../components/Field";
import { useLoad } from "../useLoad";

export function MaterialSuppliersPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const canEdit = user?.role === "administrator";
  const load = useCallback(
    () =>
      Promise.all([
        api<Item>(`/materials/${id}`),
        api<Supplier[]>("/suppliers?active_only=true"),
        api<SupplierLink[]>(`/materials/${id}/suppliers`),
      ]),
    [id],
  );
  const { data, error: loadError } = useLoad(load);
  const [linked, setLinked] = useState<number[]>([]);
  const [preferred, setPreferred] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  useEffect(() => {
    if (data) {
      setLinked(data[2].map((link) => link.supplier.id));
      setPreferred(data[2].find((link) => link.preferred)?.supplier.id ?? null);
    }
  }, [data]);

  const toggle = (supplierId: number, on: boolean) => {
    const next = on ? [...linked, supplierId] : linked.filter((s) => s !== supplierId);
    setLinked(next);
    if (!on && preferred === supplierId) setPreferred(next[0] ?? null);
    if (on && preferred === null) setPreferred(supplierId);
  };

  const save = async () => {
    setSaved("");
    try {
      const links = linked.map((supplier_id) => ({
        supplier_id,
        preferred: supplier_id === preferred,
      }));
      await api(`/materials/${id}/suppliers`, { method: "PUT", body: { links } });
      setError("");
      setSaved("Suppliers saved.");
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  const material = data?.[0];
  const shown = new Map<number, Supplier>();
  data?.[2].forEach((link) => shown.set(link.supplier.id, link.supplier));
  data?.[1].forEach((supplier) => shown.set(supplier.id, supplier));
  const suppliers = canEdit
    ? [...shown.values()]
    : [...shown.values()].filter((supplier) => linked.includes(supplier.id));

  return (
    <section>
      <p>
        <Link to="/materials">Back to raw materials</Link>
      </p>
      <h1>Suppliers{material ? `: ${material.code} ${material.name}` : ""}</h1>
      <ErrorMessage text={loadError || error} />
      <SuccessMessage text={saved} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {canEdit && <th scope="col">Approved</th>}
              <th scope="col">Preferred</th>
              <th scope="col">Supplier</th>
              <th scope="col">Lead time (days)</th>
              <th scope="col">MOQ</th>
              <th scope="col">Unit price</th>
            </tr>
          </thead>
          <tbody>
            {suppliers.map((supplier) => (
              <tr key={supplier.id}>
                {canEdit && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Approve ${supplier.code}`}
                      checked={linked.includes(supplier.id)}
                      onChange={(e) => toggle(supplier.id, e.target.checked)}
                    />
                  </td>
                )}
                <td>
                  {canEdit ? (
                    <input
                      type="radio"
                      name="preferred"
                      aria-label={`Prefer ${supplier.code}`}
                      disabled={!linked.includes(supplier.id)}
                      checked={preferred === supplier.id}
                      onChange={() => setPreferred(supplier.id)}
                    />
                  ) : preferred === supplier.id ? (
                    "Yes"
                  ) : (
                    "No"
                  )}
                </td>
                <td>
                  {supplier.code} {supplier.name}
                </td>
                <td>{supplier.lead_time_days}</td>
                <td>{supplier.moq}</td>
                <td>{supplier.unit_price.toFixed(2)}</td>
              </tr>
            ))}
            {suppliers.length === 0 && (
              <tr>
                <td colSpan={6}>No suppliers to show.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {canEdit && (
        <div className="actions">
          <button type="button" onClick={save}>
            Save suppliers
          </button>
        </div>
      )}
    </section>
  );
}
