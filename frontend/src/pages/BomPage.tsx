import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, BomLine, Item, messageOf } from "../api";
import { useAuth } from "../auth";
import { ErrorMessage, SuccessMessage } from "../components/Field";
import { useLoad } from "../useLoad";

interface Row {
  materialId: string;
  quantity: string;
}

export function BomPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const canEdit = user?.role === "administrator";
  const load = useCallback(
    () =>
      Promise.all([
        api<Item>(`/products/${id}`),
        api<Item[]>("/materials?active_only=true"),
        api<BomLine[]>(`/products/${id}/bom`),
      ]),
    [id],
  );
  const { data, error: loadError } = useLoad(load);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  useEffect(() => {
    if (data) {
      setRows(
        data[2].map((line) => ({
          materialId: String(line.material.id),
          quantity: String(line.qty_per_unit),
        })),
      );
    }
  }, [data]);

  const change = (index: number, patch: Partial<Row>) =>
    setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const save = async () => {
    setSaved("");
    if (rows.some((row) => !row.materialId)) {
      setError("Choose a material for every line.");
      return;
    }
    try {
      const lines = rows.map((row) => ({
        material_id: Number(row.materialId),
        qty_per_unit: row.quantity,
      }));
      await api(`/products/${id}/bom`, { method: "PUT", body: { lines } });
      setError("");
      setSaved("BOM saved.");
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  const product = data?.[0];
  const materials = data?.[1] ?? [];
  const names = new Map(data?.[2].map((line) => [String(line.material.id), line.material]));
  materials.forEach((material) => names.set(String(material.id), material));

  return (
    <section>
      <p>
        <Link to="/products">Back to products</Link>
      </p>
      <h1>Bill of materials{product ? `: ${product.code} ${product.name}` : ""}</h1>
      <p className="hint">Quantity of each raw material needed to make one unit of this product.</p>
      <ErrorMessage text={loadError || error} />
      <SuccessMessage text={saved} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Material</th>
              <th scope="col">Quantity per unit</th>
              {canEdit && <th scope="col">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td>
                  {canEdit ? (
                    <select
                      aria-label={`Material for line ${index + 1}`}
                      value={row.materialId}
                      onChange={(e) => change(index, { materialId: e.target.value })}
                    >
                      <option value="">Choose...</option>
                      {[...names.values()].map((material) => (
                        <option key={material.id} value={material.id}>
                          {material.code} {material.name} ({material.unit})
                        </option>
                      ))}
                    </select>
                  ) : (
                    `${names.get(row.materialId)?.code} ${names.get(row.materialId)?.name}`
                  )}
                </td>
                <td>
                  {canEdit ? (
                    <input
                      aria-label={`Quantity for line ${index + 1}`}
                      type="number"
                      min="0.0001"
                      step="any"
                      value={row.quantity}
                      onChange={(e) => change(index, { quantity: e.target.value })}
                    />
                  ) : (
                    row.quantity
                  )}
                </td>
                {canEdit && (
                  <td>
                    <button
                      type="button"
                      className="link"
                      onClick={() => setRows(rows.filter((_, i) => i !== index))}
                    >
                      Remove <span className="sr-only">line {index + 1}</span>
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={3}>No materials in this BOM yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {canEdit && (
        <div className="actions">
          <button
            type="button"
            className="secondary"
            onClick={() => setRows([...rows, { materialId: "", quantity: "1" }])}
          >
            Add line
          </button>
          <button type="button" onClick={save}>
            Save BOM
          </button>
        </div>
      )}
    </section>
  );
}
