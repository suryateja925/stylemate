import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, frontendConfigurationReady, useAuth } from "./auth";
import { AuthScreen } from "./components/AuthScreen";
import { Layout } from "./components/Layout";

const Dashboard = lazy(() => import("./pages/Dashboard").then((module) => ({ default: module.Dashboard })));
const History = lazy(() => import("./pages/History").then((module) => ({ default: module.History })));
const Plans = lazy(() => import("./pages/Plans").then((module) => ({ default: module.Plans })));
const PreferencesPage = lazy(() => import("./pages/Preferences").then((module) => ({ default: module.PreferencesPage })));
const Recommendations = lazy(() => import("./pages/Recommendations").then((module) => ({ default: module.Recommendations })));
const Scanner = lazy(() => import("./pages/Scanner").then((module) => ({ default: module.Scanner })));
const Settings = lazy(() => import("./pages/Settings").then((module) => ({ default: module.Settings })));
const Wardrobe = lazy(() => import("./pages/Wardrobe").then((module) => ({ default: module.Wardrobe })));

function ApplicationRoutes() {
  const { loading, mode, recoveryRequired, session } = useAuth();
  if (!frontendConfigurationReady) {
    return <main className="grid min-h-screen place-items-center bg-slate-50 p-6"><section className="max-w-xl rounded-3xl border border-amber-200 bg-white p-8"><h1 className="text-xl font-bold">Deployment configuration required</h1><p className="mt-3 text-sm leading-6 text-slate-600">Set VITE_API_URL, VITE_SUPABASE_URL, and VITE_SUPABASE_PUBLISHABLE_KEY in the Vercel project settings, then redeploy.</p></section></main>;
  }
  if (loading) return <main className="grid min-h-screen place-items-center text-sm text-slate-500">Loading your secure session...</main>;
  if (mode === "unconfigured") return <main className="grid min-h-screen place-items-center p-6 text-center"><p>Authentication is not configured. Contact the site administrator.</p></main>;
  if (recoveryRequired) return <AuthScreen />;
  if (mode === "supabase" && !session) return <AuthScreen />;

  return <BrowserRouter><Suspense fallback={<main className="grid min-h-screen place-items-center text-sm text-slate-500">Loading page...</main>}><Routes><Route element={<Layout />}><Route index element={<Dashboard />} /><Route path="plans" element={<Plans />} /><Route path="recommendations" element={<Recommendations />} /><Route path="scanner" element={<Scanner />} /><Route path="wardrobe" element={<Wardrobe />} /><Route path="history" element={<History />} /><Route path="preferences" element={<PreferencesPage />} /><Route path="settings" element={<Settings />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes></Suspense></BrowserRouter>;
}

export default function App() {
  return <AuthProvider><ApplicationRoutes /></AuthProvider>;
}
