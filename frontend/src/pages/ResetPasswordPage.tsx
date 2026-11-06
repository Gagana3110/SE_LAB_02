import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, messageOf } from "../api";
import { ErrorMessage, Field, SuccessMessage } from "../components/Field";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api("/auth/password-reset/confirm", {
        method: "POST",
        body: { token: params.get("token") ?? "", new_password: password },
      });
      setDone(true);
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  return (
    <main className="login">
      <form className="card" onSubmit={submit}>
        <h1>Choose a new password</h1>
        <ErrorMessage text={error} />
        <SuccessMessage text={done ? "Your password has been changed. You can log in now." : ""} />
        <Field label="New password (at least 8 characters)" type="password" minLength={8}
               autoComplete="new-password" required value={password}
               onChange={(e) => setPassword(e.target.value)} />
        <button type="submit" disabled={done}>Change password</button>
        <p className="hint"><Link to="/">Back to log in</Link></p>
      </form>
    </main>
  );
}