import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session, SupabaseClient, User } from "@supabase/supabase-js";
import { api, setAccessTokenProvider } from "./api";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim() ?? "";
const supabasePublishableKey = (
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
  ?? import.meta.env.VITE_SUPABASE_ANON_KEY
)?.trim() ?? "";
const hasSupabaseConfiguration = Boolean(supabaseUrl && supabasePublishableKey);

let supabaseClient: SupabaseClient | null = null;

function getSupabaseClient(): SupabaseClient {
  if (!supabaseClient) throw new Error("Supabase authentication is not ready.");
  return supabaseClient;
}

export type AuthMode = "local" | "supabase" | "unconfigured";

type AuthContextValue = {
  mode: AuthMode;
  loading: boolean;
  session: Session | null;
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<boolean>;
  sendPasswordReset: (email: string) => Promise<void>;
  updatePassword: (password: string) => Promise<void>;
  deleteAccount: () => Promise<void>;
  recoveryRequired: boolean;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const mode: AuthMode = hasSupabaseConfiguration ? "supabase" : import.meta.env.DEV ? "local" : "unconfigured";
  const [session, setSession] = useState<Session | null>(null);
  const [recoveryRequired, setRecoveryRequired] = useState(false);
  const [loading, setLoading] = useState(mode === "supabase");

  useEffect(() => {
    if (mode !== "supabase") {
      setLoading(false);
      setAccessTokenProvider(async () => null);
      return;
    }

    let active = true;
    let unsubscribe: (() => void) | undefined;
    void import("@supabase/supabase-js").then(({ createClient }) => {
      if (!active) return;
      const client = createClient(supabaseUrl, supabasePublishableKey, {
        auth: {
          autoRefreshToken: true,
          persistSession: true,
          detectSessionInUrl: true,
        },
      });
      supabaseClient = client;
      setAccessTokenProvider(async () => {
        const { data, error } = await client.auth.getSession();
        if (error) throw error;
        return data.session?.access_token ?? null;
      });
      const { data: { subscription } } = client.auth.onAuthStateChange((event, nextSession) => {
        if (active) {
          setSession(nextSession);
          if (event === "PASSWORD_RECOVERY") setRecoveryRequired(true);
          if (event === "SIGNED_OUT") setRecoveryRequired(false);
          setLoading(false);
        }
      });
      unsubscribe = () => subscription.unsubscribe();
      void client.auth.getSession().then(({ data, error }) => {
        if (!active) return;
        if (!error) setSession(data.session);
        setLoading(false);
      }).catch(() => {
        if (active) setLoading(false);
      });
    }).catch(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
      unsubscribe?.();
      supabaseClient = null;
      setAccessTokenProvider(async () => null);
    };
  }, [mode]);

  const value = useMemo<AuthContextValue>(() => ({
    mode,
    loading,
    session,
    user: session?.user ?? null,
    recoveryRequired,
    signIn: async (email, password) => {
      const { error } = await getSupabaseClient().auth.signInWithPassword({ email, password });
      if (error) throw error;
    },
    signUp: async (email, password) => {
      const { data, error } = await getSupabaseClient().auth.signUp({ email, password });
      if (error) throw error;
      return !data.session;
    },
    sendPasswordReset: async (email) => {
      const { error } = await getSupabaseClient().auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
      if (error) throw error;
    },
    updatePassword: async (password) => {
      const { error } = await getSupabaseClient().auth.updateUser({ password });
      if (error) throw error;
      setRecoveryRequired(false);
    },
    deleteAccount: async () => {
      await api.deleteAccount();
      if (supabaseClient) {
        const { error } = await supabaseClient.auth.signOut({ scope: "local" });
        if (error) throw error;
      }
    },
    signOut: async () => {
      const { error } = await getSupabaseClient().auth.signOut();
      if (error) throw error;
    },
  }), [loading, mode, recoveryRequired, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}

export const frontendConfigurationReady = !import.meta.env.PROD
  || Boolean(import.meta.env.VITE_API_URL?.trim() && hasSupabaseConfiguration);
