"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { authApi, PASSWORD_MIN } from "../lib/auth";
import { useAuth } from "../components/Auth";
import { pageAfterLogin } from "../components/AuthNudge";

const message = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong. Try again.");

// Google's script opens its sign-in popup from our own "Continue with Google" link and hands back an access token
type TokenClient = { requestAccessToken: () => void };
type GoogleOAuth = {
  initTokenClient: (o: {
    client_id: string;
    scope: string;
    callback: (r: { access_token?: string; error?: string }) => void;
    error_callback?: (e: { type: string }) => void;
  }) => TokenClient;
};
let gisLoading: Promise<void> | null = null;
function loadGoogle(): Promise<void> {
  gisLoading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Couldn't load Google sign-in."));
    document.head.appendChild(s);
  });
  return gisLoading;
}

function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { user, ready, signIn, signUp, signInWithGoogle } = useAuth();
  // undefined: not asked yet; null: this server has no Google sign-in
  const [googleId, setGoogleId] = useState<string | null | undefined>(undefined);
  const [inForm, setInForm] = useState({ email: "", password: "" });
  const [upForm, setUpForm] = useState({ name: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState<{ where: "in" | "up" | "google"; text: string } | null>(null);
  const [busy, setBusy] = useState<"in" | "up" | "google" | null>(null);
  const upPanel = useRef<HTMLElement>(null);
  const google = useRef<TokenClient | null>(null);
  const mismatch = upForm.confirm !== "" && upForm.confirm !== upForm.password;

  useEffect(() => {
    authApi.config().then((c) => setGoogleId(c.google_client_id)).catch(() => setGoogleId(null));
  }, []);

  // get Google's popup ready before the click, so the browser doesn't treat it as an unrequested popup
  const finish = useRef<(token: string) => void>(() => {});
  finish.current = (token) => void run("google", () => signInWithGoogle(token));
  useEffect(() => {
    if (!googleId) return;
    let cancelled = false;
    loadGoogle()
      .then(() => {
        const g = (window as unknown as { google?: { accounts: { oauth2: GoogleOAuth } } }).google;
        if (cancelled || !g) return;
        google.current = g.accounts.oauth2.initTokenClient({
          client_id: googleId,
          scope: "openid email profile",
          callback: (r) => (r.access_token ? finish.current(r.access_token) : setError({ where: "google", text: "Google couldn't confirm this sign-in. Try again." })),
          error_callback: (e) => e.type !== "popup_closed" && setError({ where: "google", text: "Google sign-in didn't open. Allow pop-ups for this site and try again." }),
        });
      })
      .catch((e) => !cancelled && setError({ where: "google", text: message(e) }));
    return () => {
      cancelled = true;
    };
  }, [googleId]);

  function continueWithGoogle() {
    if (googleId === null) setError({ where: "google", text: "Google sign-in isn't set up on this server yet." });
    else if (google.current) google.current.requestAccessToken();
    else setError({ where: "google", text: "Google sign-in is still loading. Try again in a moment." });
  }

  // /login#signup brings the sign-up side into view (they're stacked on a phone)
  useEffect(() => {
    if (window.location.hash === "#signup") upPanel.current?.scrollIntoView({ block: "center" });
  }, []);

  // already signed in: back to the app (the page they came from, when we know it)
  useEffect(() => {
    if (ready && user) router.replace(`/${pageAfterLogin()}`);
  }, [ready, user, router]);

  async function run(where: "in" | "up" | "google", job: () => Promise<void>) {
    if (busy) return;
    setBusy(where);
    setError(null);
    try {
      await job();
    } catch (e) {
      setError({ where, text: e instanceof ApiError || e instanceof Error ? e.message : "Something went wrong. Try again." });
      setBusy(null);
    }
  }

  const fail = (where: "in" | "up" | "google") => error?.where === where && <p className="auth-error" role="alert">{error.text}</p>;

  return (
    <main className="auth-page">
      <section className="auth-card auth-wide glass" aria-label="Sign in or sign up">
        <Link href="/" className="auth-brand" aria-label="Back to Kompas">
          <img src="/kompas_logo.png" alt="Kompas" />
        </Link>

        <div className="auth-cols">
          <section aria-labelledby="signin-title">
            <h1 id="signin-title">Sign in</h1>
            <p className="muted">Pick up your learning route where you left off.</p>
            <form className="auth-form" onSubmit={(e) => { e.preventDefault(); void run("in", () => signIn(inForm.email, inForm.password)); }}>
              <label>
                <span>Email</span>
                <input type="email" value={inForm.email} onChange={(e) => setInForm({ ...inForm, email: e.target.value })}
                  autoComplete="username" required maxLength={254} />
              </label>
              <label>
                <span>Password</span>
                <input type="password" value={inForm.password} onChange={(e) => setInForm({ ...inForm, password: e.target.value })}
                  autoComplete="current-password" required maxLength={128} />
              </label>
              {fail("in")}
              <button className="btn btn-primary" type="submit" disabled={!!busy || !inForm.email || !inForm.password}>
                {busy === "in" ? "One moment…" : "Sign in"}
              </button>
            </form>
          </section>

          <span className="auth-divider" aria-hidden />

          <section ref={upPanel} aria-labelledby="signup-title">
            <h1 id="signup-title">Sign up</h1>
            <p className="muted">An account saves your learning progress, so you can continue on any device.</p>
            <form className="auth-form" onSubmit={(e) => { e.preventDefault(); void run("up", async () => {
              if (upForm.confirm !== upForm.password) throw new Error("The two passwords don't match.");
              await signUp(upForm.email, upForm.password, upForm.name);
            }); }}>
              <label>
                <span>Name <span className="muted">(optional)</span></span>
                <input value={upForm.name} onChange={(e) => setUpForm({ ...upForm, name: e.target.value })} autoComplete="name" maxLength={40} />
              </label>
              <label>
                <span>Email</span>
                <input type="email" value={upForm.email} onChange={(e) => setUpForm({ ...upForm, email: e.target.value })}
                  autoComplete="email" required maxLength={254} />
              </label>
              <label>
                <span>Password</span>
                <input type="password" value={upForm.password} onChange={(e) => setUpForm({ ...upForm, password: e.target.value })}
                  autoComplete="new-password" required minLength={PASSWORD_MIN} maxLength={128} />
                <small className="muted">At least {PASSWORD_MIN} characters.</small>
              </label>
              <label>
                <span>Confirm password</span>
                <input type="password" value={upForm.confirm} onChange={(e) => setUpForm({ ...upForm, confirm: e.target.value })}
                  autoComplete="new-password" required maxLength={128} aria-invalid={mismatch} aria-describedby={mismatch ? "confirm-note" : undefined} />
                {mismatch && <small id="confirm-note" className="auth-mismatch">The two passwords don&apos;t match.</small>}
              </label>
              {fail("up")}
              <button className="btn btn-primary" type="submit" disabled={!!busy || !upForm.email || !upForm.password || !upForm.confirm || mismatch}>
                {busy === "up" ? "One moment…" : "Create account"}
              </button>
            </form>
          </section>
        </div>

        <p className="muted small auth-foot">
          <button type="button" className="sim-link auth-google-link" onClick={continueWithGoogle}>
            <GoogleLogo /> Continue with Google
          </button>
          <span aria-hidden>·</span>
          <Link href="/" className="sim-link">Continue without an account</Link>
        </p>
        {fail("google")}
      </section>
    </main>
  );
}
