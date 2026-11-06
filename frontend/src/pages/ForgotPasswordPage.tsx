import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, messageOf } from "../api";
import { ErrorMessage, Field, SuccessMessage } from "../components/Field";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api("/auth/password-reset/request", { method: "POST", body: { email } });
      setSent(true);
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  return (
    <main className="login">
      <form className="card" onSubmit={submit}>
        <h1>Reset your password</h1>
        <ErrorMessage text={error} />
        <SuccessMessage
          text={sent ? "If that email has an account, a reset link has been sent. It works for 30 minutes." : ""}
        />
        <Field label="Email" type="email" required value={email}
               onChange={(e) => setEmail(e.target.value)} />
        <button type="submit">Send reset link</button>
        <p className="hint"><Link to="/">Back to log in</Link></p>
      </form>
    </main>
  );
}