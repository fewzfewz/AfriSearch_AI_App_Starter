// Sign-in: Supabase Auth when the server uses it, otherwise everyone is the local user.
import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setTokenGetter } from "./api";
import type { AppConfig } from "./types";

interface AuthState {
  config: AppConfig | null;
  configError: string | null;
  /** True once we know whether someone is signed in. */
  ready: boolean;
  signedIn: boolean;
  email: string;
  supabase: SupabaseClient | null;
  /** Set when the user arrived from a password-reset email. */
  recovering: boolean;
  finishRecovery: () => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [recovering, setRecovering] = useState(false);

  useEffect(() => {
    api<AppConfig>("/config")
      .then((loaded) => {
        setConfig(loaded);
        // Error reporting is only downloaded when the server has a Sentry DSN for the web app.
        if (loaded.sentry_dsn) {
          import("@sentry/browser").then((Sentry) =>
            Sentry.init({ dsn: loaded.sentry_dsn!, environment: loaded.environment, release: `afrisearch@${loaded.version}`, sendDefaultPii: false }),
          );
        }
      })
      .catch((error: Error) => setConfigError(error.message));
  }, []);

  const [supabase, setSupabase] = useState<SupabaseClient | null>(null);

  // The Supabase library is only downloaded when this server uses sign-in.
  useEffect(() => {
    if (!config) return;
    if (config.auth !== "supabase" || !config.supabase_url || !config.supabase_anon_key) {
      setTokenGetter(async () => null);
      setReady(true);
      return;
    }
    let cancelled = false;
    import("@supabase/supabase-js")
      .then(({ createClient }) => !cancelled && setSupabase(createClient(config.supabase_url!, config.supabase_anon_key!)))
      .catch((error: Error) => setConfigError(`Couldn't load sign-in: ${error.message}`));
    return () => {
      cancelled = true;
    };
  }, [config]);

  useEffect(() => {
    if (!supabase) return;
    setTokenGetter(async () => (await supabase.auth.getSession()).data.session?.access_token ?? null);
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((event, next) => {
      setSession(next);
      if (event === "PASSWORD_RECOVERY") setRecovering(true);
    });
    return () => data.subscription.unsubscribe();
  }, [supabase]);

  const value: AuthState = {
    config,
    configError,
    ready,
    signedIn: config?.auth === "none" || Boolean(session),
    email: session?.user.email ?? "",
    supabase,
    recovering,
    finishRecovery: () => setRecovering(false),
    signOut: async () => {
      await supabase?.auth.signOut();
      setSession(null);
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}
