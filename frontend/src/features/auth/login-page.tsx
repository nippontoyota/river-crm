"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { cacheCurrentUser, login } from "@/lib/crm";

export function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setLoading(true); setError("");
    const formData = new FormData(event.currentTarget);
    const submittedEmail = String(formData.get("email") || "").trim();
    const submittedPassword = String(formData.get("password") || "");
    try { const result = await login(submittedEmail, submittedPassword); cacheCurrentUser(result.user); router.push(result.user.role === "ADMIN" ? "/leads" : result.user.role === "SALES_MANAGER" ? "/manager/analytics" : result.user.role === "RECEPTIONIST" ? "/capture" : result.user.role === "COMPLAINTS" ? "/complaints" : "/my-leads"); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to sign in."); }
    finally { setLoading(false); }
  };
  return (
    <main className="login-page">
      <section className="login-visual" aria-labelledby="login-visual-title">
        <div className="login-visual-copy">
          <p>Incheon Mobility LLP</p>
          <h2 id="login-visual-title">Move every lead forward.</h2>
        </div>
        <span className="login-mobility-word" aria-hidden="true">MOBILITY</span>
        <div className="login-route" aria-hidden="true">
          <span className="login-route-node enquiry">Enquiry</span>
          <span className="login-route-node follow-up">Follow-up</span>
          <span className="login-route-node delivery">Delivery</span>
        </div>
      </section>

      <section className="login-access">
        <div className="login-card">
          <p className="login-wordmark"><strong>Incheon</strong> Mobility</p>
          <p className="login-product">Dealer operations CRM</p>
          <p className="login-dealer"><span aria-hidden="true" />Authorized River Dealer</p>
          <div className="login-heading">
            <h1>Welcome back.</h1>
            <p>Sign in with the account created by your administrator.</p>
          </div>

          <form className="auth-form" onSubmit={submit}>
            <label htmlFor="login-email">
              Email
              <input
                id="login-email"
                name="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
              />
            </label>
            <label htmlFor="login-password">
              Password
              <div className="password-field">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  autoComplete="current-password"
                />
                <button
                  className="password-toggle"
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d={showPassword ? "M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A10.7 10.7 0 0 1 12 5c5.2 0 8.4 5.3 9.5 7a17.8 17.8 0 0 1-3.2 3.7M6.2 6.2C3.9 7.7 2.7 10 2.5 12c1.1 1.7 4.3 7 9.5 7 1 0 1.9-.2 2.7-.5" : "M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7Z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"} />
                  </svg>
                </button>
              </div>
            </label>
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button className="login-submit" disabled={loading}>{loading ? "Signing in…" : "Sign in"}</button>
          </form>

          <p className="login-note">Authorized team access only</p>
        </div>
      </section>
    </main>
  );
}
