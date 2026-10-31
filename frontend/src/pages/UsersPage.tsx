import { FormEvent, useCallback, useState } from "react";
import { api, messageOf, Role, User } from "../api";
import { ROLE_LABELS } from "../auth";
import { ErrorMessage, Field } from "../components/Field";
import { useLoad } from "../useLoad";

const loadUsers = () => api<User[]>("/users");

export function UsersPage() {
  const { data: users, error: loadError, reload } = useLoad(useCallback(loadUsers, []));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("demand_planner");
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await api("/users", { method: "POST", body: { email, password, role } });
      setEmail("");
      setPassword("");
      setError("");
      await reload();
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  return (
    <section>
      <h1>Users</h1>
      <ErrorMessage text={loadError} />
      <form className="card form-row" onSubmit={save}>
        <h2>Add a user</h2>
        <ErrorMessage text={error} />
        <div className="fields">
          <Field
            label="Email"
            type="email"
            required
            autoComplete="off"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Field
            label="Temporary password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <label className="field">
            <span>Role</span>
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {(Object.keys(ROLE_LABELS) as Role[]).map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="actions">
          <button type="submit">Add user</button>
        </div>
      </form>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
            </tr>
          </thead>
          <tbody>
            {users?.map((user) => (
              <tr key={user.id}>
                <td>{user.email}</td>
                <td>{ROLE_LABELS[user.role]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
