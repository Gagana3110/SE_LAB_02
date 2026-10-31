import { FormEvent, useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { api, Item, messageOf } from "../api";
import { useAuth } from "../auth";
import { ErrorMessage, Field } from "../components/Field";
import { useLoad } from "../useLoad";

interface ItemsPageProps {
  kind: "products" | "materials";
  title: string;
}

const EMPTY = { code: "", name: "", unit: "", category: "" };

export function ItemsPage({ kind, title }: ItemsPageProps) {
  const { user } = useAuth();
  const canEdit = user?.role === "administrator";
  const load = useCallback(() => api<Item[]>(`/${kind}`), [kind]);
  const { data: items, error: loadError, reload } = useLoad(load);
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
    const body = { ...form, category: form.category.trim() || null };
    try {
      await (editing === null
        ? api(`/${kind}`, { method: "POST", body })
        : api(`/${kind}/${editing}`, { method: "PATCH", body }));
      reset();
      await reload();
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  const edit = (item: Item) => {
    setForm({ code: item.code, name: item.name, unit: item.unit, category: item.category ?? "" });
    setEditing(item.id);
    setError("");
  };

  const setActive = async (item: Item, active: boolean) => {
    try {
      await api(`/${kind}/${item.id}`, { method: "PATCH", body: { active } });
      setError("");
      await reload();
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  return (
    <section>
      <h1>{title}</h1>
      <ErrorMessage text={loadError} />
      {canEdit && (
        <form className="card form-row" onSubmit={save}>
          <h2>{editing === null ? "Add new" : `Edit ${form.code}`}</h2>
          <ErrorMessage text={error} />
          <div className="fields">
            <Field label="Code" required maxLength={32} value={form.code} onChange={set("code")} />
            <Field label="Name" required maxLength={120} value={form.name} onChange={set("name")} />
            <Field label="Unit" required maxLength={20} value={form.unit} onChange={set("unit")} />
            <Field label="Category" maxLength={60} value={form.category} onChange={set("category")} />
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
              <th scope="col">Unit</th>
              <th scope="col">Category</th>
              <th scope="col">Status</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items?.map((item) => (
              <tr key={item.id}>
                <td>{item.code}</td>
                <td>{item.name}</td>
                <td>{item.unit}</td>
                <td>{item.category ?? "-"}</td>
                <td>
                  <span className={item.active ? "badge ok" : "badge off"}>
                    {item.active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="row-actions">
                  {kind === "products" ? (
                    <Link to={`/products/${item.id}/bom`}>BOM</Link>
                  ) : (
                    (user?.role === "administrator" || user?.role === "procurement_manager") && (
                      <Link to={`/materials/${item.id}/suppliers`}>Suppliers</Link>
                    )
                  )}
                  {canEdit && (
                    <>
                      <button type="button" className="link" onClick={() => edit(item)}>
                        Edit <span className="sr-only">{item.code}</span>
                      </button>
                      <button
                        type="button"
                        className="link"
                        onClick={() => setActive(item, !item.active)}
                      >
                        {item.active ? "Deactivate" : "Activate"}{" "}
                        <span className="sr-only">{item.code}</span>
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {items?.length === 0 && (
              <tr>
                <td colSpan={6}>Nothing added yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
