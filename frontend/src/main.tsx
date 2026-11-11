import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router";
import { AppLayout } from "./components/Layout";
import { Spinner } from "./components/ui";
import "./index.css";
import { ApiError } from "./lib/api";
import { SessionProvider, useSession } from "./lib/session";
import ActionItemsPage from "./pages/ActionItems";
import AnalyticsPage from "./pages/Analytics";
import AssistantPage from "./pages/Assistant";
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage } from "./pages/Auth";
import DecisionsPage from "./pages/Decisions";
import DemoPage from "./pages/Demo";
import MeetingDetailPage from "./pages/MeetingDetail";
import MeetingsPage from "./pages/Meetings";
import NotFoundPage from "./pages/NotFound";
import OverviewPage from "./pages/Overview";
import PrivacyPage from "./pages/Privacy";
import { ProjectDetailPage, ProjectsPage } from "./pages/Projects";
import ReportsPage from "./pages/Reports";
import SearchPage from "./pages/Search";
import SettingsPage from "./pages/Settings";
import TranscriptsPage from "./pages/Transcripts";
import UploadPage from "./pages/Upload";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
    },
  },
});

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading, workspace } = useSession();
  const location = useLocation();
  if (loading) return <Spinner label="Loading your workspace" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!workspace) return <Spinner label="Loading your workspace" />;
  return <>{children}</>;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useSession();
  if (loading) return <Spinner />;
  return user ? <Navigate to="/" replace /> : <>{children}</>;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
      <Route path="/register" element={<GuestOnly><RegisterPage /></GuestOnly>} />
      <Route path="/forgot-password" element={<GuestOnly><ForgotPasswordPage /></GuestOnly>} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/demo" element={<DemoPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route index element={<OverviewPage />} />
        <Route path="meetings" element={<MeetingsPage />} />
        <Route path="meetings/:id" element={<MeetingDetailPage />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="transcripts" element={<TranscriptsPage />} />
        <Route path="action-items" element={<ActionItemsPage />} />
        <Route path="decisions" element={<DecisionsPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:id" element={<ProjectDetailPage />} />
        <Route path="assistant" element={<AssistantPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
