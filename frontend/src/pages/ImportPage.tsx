import { FormEvent, useState } from "react";
import { api, ImportResult, messageOf } from "../api";
import { ErrorMessage } from "../components/Field";

const MAX_BYTES = 10 * 1024 * 1024;

export function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setResult(null);
    if (file.size > MAX_BYTES) {
      setError("This file is larger than the 10 MB limit.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setResult(await api<ImportResult>("/imports/sales", { method: "POST", file }));
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h1>Import sales history</h1>
      <form className="card" onSubmit={submit}>
        <p className="hint">
          Upload a .csv or .xlsx file up to 10 MB with the columns <code>date</code> (YYYY-MM-DD),{" "}
          <code>product_code</code>, <code>quantity</code> and optionally <code>region</code>.
          Importing the same period again updates the existing figures.
        </p>
        <ErrorMessage text={error} />
        <label className="field">
          <span>Sales file</span>
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <div className="actions">
          <button type="submit" disabled={busy || !file}>
            {busy ? "Importing..." : "Import"}
          </button>
        </div>
      </form>

      {result && (
        <div className="card" role="status">
          <h2>Import summary: {result.filename}</h2>
          <dl className="stats">
            <div>
              <dt>New rows</dt>
              <dd>{result.imported}</dd>
            </div>
            <div>
              <dt>Updated rows</dt>
              <dd>{result.updated}</dd>
            </div>
            <div>
              <dt>Rejected rows</dt>
              <dd>{result.rejected}</dd>
            </div>
          </dl>
          {result.rejected > 0 && (
            <>
              <p>
                <a href={`/api/imports/${result.id}/errors.csv`}>Download the error report</a>
              </p>
              <div className="table-wrap">
                <table>
                  <caption>
                    Rows that were not imported
                    {result.errors.length < result.rejected &&
                      ` (first ${result.errors.length} of ${result.rejected})`}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Row</th>
                      <th scope="col">Column</th>
                      <th scope="col">Problem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.errors.slice(0, 50).map((row) => (
                      <tr key={`${row.row}-${row.field}`}>
                        <td>{row.row}</td>
                        <td>{row.field}</td>
                        <td>{row.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
