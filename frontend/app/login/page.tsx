"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import { PASSWORD_MIN } from "../lib/auth";
import { useAuth } from "../components/Auth";
import { pageAfterLogin } from "../components/AuthNudge";

type Mode = "in" | "up";

export default function LoginPage() {
  const router = useRouter();
  const { user, ready, signIn, signUp } = useAuth();
  const [mode, setMode] = useState<Mode>("in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // /login#signup opens on the sign-up tab
  useEffect(() => {
    if (window.location.hash === "#signup") setMode("up");
  }, []);

  // already signed in: back to the app (the page they came from, when we know it)
  useEffect(() => {
    if (ready && user) router.replace(`/${pageAfterLogin()}`);
  }, [ready, user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "in") await signIn(email, password);
      else await signUp(email, password, name);
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  function pick(next: Mode) {
    setMode(next);
    setError(null);
  }

  return (
    <main className="auth-page">
      <section className="auth-card glass" aria-labelledby="auth-title">
        <Link href="/" className="brand" aria-label="Back to Kompas">
          <img src="/kompas_logo.png" alt="" className="brand-mark" />
          Kompas
        </Link>

        <div className="auth-tabs" role="tablist" aria-label="Sign in or sign up">
          <button role="tab" aria-selected={mode === "in"} className={mode === "in" ? "on" : ""} onClick={() => pick("in")}>Sign in</button>
          <button role="tab" aria-selected={mode === "up"} className={mode === "up" ? "on" : ""} onClick={() => pick("up")}>Sign up</button>
        </div>

        <div>
          <h1 id="auth-title">{mode === "in" ? "Welcome back" : "Create your account"}</h1>
          <p className="muted">
            {mode === "in"
              ? "Sign in to pick up your learning route where you left off."
              : "An account saves your learning progress, so you can continue on any device."}
          </p>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {mode === "up" && (
            <label>
              <span>Name <span className="muted">(optional)</span></span>
              <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={40} />
            </label>
          )}
          <label>
            <span>Email</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required maxLength={254} />
          </label>
          <label>
            <span>Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "in" ? "current-password" : "new-password"} required minLength={mode === "up" ? PASSWORD_MIN : undefined} maxLength={128} />
            {mode === "up" && <small className="muted">At least {PASSWORD_MIN} characters.</small>}
          </label>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button className="btn btn-primary" type="submit" disabled={busy || !email || !password}>
            {busy ? "One moment…" : mode === "in" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p className="muted small">
          {mode === "in" ? "New here? " : "Already have an account? "}
          <button className="sim-link" onClick={() => pick(mode === "in" ? "up" : "in")}>{mode === "in" ? "Create an account" : "Sign in"}</button>
          {" · "}
          <Link href="/" className="sim-link">Continue without an account</Link>
        </p>
      </section>
    </main>
  );
}
