import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Button, Logo, Spinner, ToastProvider } from "./components/ui";
import { AuthProvider, useAuth } from "./lib/auth";
import { useTheme } from "./lib/theme";
import { WorkspaceProvider } from "./lib/workspace";
import { LandingPage } from "./pages/LandingPage";

// The landing page loads first; the app and sign-in are fetched when opened.
const AppLayout = lazy(() => import("./pages/AppLayout").then((m) => ({ default: m.AppLayout })));
const ChatPage = lazy(() => import("./pages/ChatPage").then((m) => ({ default: m.ChatPage })));
const InsightsPage = lazy(() => import("./pages/InsightsPage").then((m) => ({ default: m.InsightsPage })));
const LibraryPage = lazy(() => import("./pages/LibraryPage").then((m) => ({ default: m.LibraryPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const SignInPage = lazy(() => import("./pages/SignInPage").then((m) => ({ default: m.SignInPage })));

function Loading() {
  return <div className="flex min-h-screen items-center justify-center"><Spinner className="h-6 w-6" /></div>;
}

function RequireSignIn({ children }: { children: JSX.Element }) {
  const { ready, signedIn } = useAuth();
  const location = useLocation();
  if (!ready) return <Loading />;
  if (!signedIn) return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  return children;
}

function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <Logo />
      <h1 className="text-2xl font-bold">Page not found</h1>
      <a href="/"><Button>Go home</Button></a>
    </div>
  );
}

function Routed() {
  const { config, configError } = useAuth();
  useTheme(); // applies the saved light/dark preference
  if (configError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-center">
        <div>
          <Logo />
          <p className="mt-6 font-semibold">Can't reach the AfriSearch server</p>
          <p className="mt-1 text-sm text-ink-500">{configError}</p>
          <Button className="mt-4" onClick={() => window.location.reload()}>Try again</Button>
        </div>
      </div>
    );
  }
  if (!config) return <Loading />;
  return (
    <Suspense fallback={<Loading />}>
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/signin" element={<SignInPage />} />
      <Route
        path="/app"
        element={
          <RequireSignIn>
            <WorkspaceProvider>
              <AppLayout />
            </WorkspaceProvider>
          </RequireSignIn>
        }
      >
        <Route index element={<ChatPage />} />
        <Route path="chat/:chatId" element={<ChatPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
    </Suspense>
  );
}

export function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <Routed />
      </ToastProvider>
    </AuthProvider>
  );
}
