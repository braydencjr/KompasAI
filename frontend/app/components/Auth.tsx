"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import { authApi, getToken, setToken, type AuthUser } from "../lib/auth";

type AuthState = {
  user: AuthUser | null;
  /** the saved sign-in has been checked (before this, `user` is null even for someone signed in) */
  ready: boolean;
  token: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signInWithGoogle: (credential: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const saved = getToken();
    if (!saved) {
      setReady(true);
      return;
    }
    authApi
      .me(saved)
      .then(({ user }) => {
        setUser(user);
        setTokenState(saved);
      })
      .catch((e) => {
        // an expired or revoked sign-in is forgotten; a server that's just unreachable keeps it for next time
        if (e instanceof ApiError && e.status === 401) setToken(null);
      })
      .finally(() => setReady(true));
  }, []);

  const start = useCallback((s: { token: string; user: AuthUser }) => {
    setToken(s.token);
    setTokenState(s.token);
    setUser(s.user);
  }, []);

  const value: AuthState = {
    user,
    ready,
    token,
    signIn: async (email, password) => start(await authApi.signIn(email, password)),
    signUp: async (email, password, name) => start(await authApi.signUp(email, password, name)),
    signInWithGoogle: async (credential) => start(await authApi.google(credential)),
    signOut: async () => {
      const t = token;
      setToken(null);
      setTokenState(null);
      setUser(null);
      if (t) await authApi.signOut(t).catch(() => {});
    },
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
