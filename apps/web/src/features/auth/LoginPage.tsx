import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiErrorMessage } from "../../api/client";
import { useSession } from "../../auth/session";

export default function LoginPage() {
  const { login } = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email, password);
      navigate("/documents", { replace: true });
    } catch (reason: unknown) {
      setError(apiErrorMessage(reason));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="panel">
      <h2>Sign in</h2>
      <form className="form" onSubmit={onSubmit}>
        <label>
          Email
          <input
            type="email"
            name="email"
            autoComplete="username"
            value={email}
            required
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            required
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit" disabled={pending}>
          Sign in
        </button>
      </form>
    </section>
  );
}
