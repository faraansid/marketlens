import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "./app/AppLayout";
import { MODULES, modulesFor } from "./app/modules";
import { EmptyState, Skeleton } from "./components/ui";
import { useAuth } from "./lib/auth";
import LandingPage from "./pages/LandingPage";
import { ChangePasswordPage, SignInPage } from "./pages/AuthPages";

const StockDetailPage = lazy(() => import("./pages/StockDetailPage"));

function FullScreenLoader() {
  return (
    <div className="flex min-h-full items-center justify-center">
      <div className="w-64 space-y-3"><Skeleton className="h-6 w-32" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-2/3" /></div>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <FullScreenLoader />;
  if (!user) return <Navigate to="/signin" replace state={{ from: loc.pathname + loc.search }} />;
  return <>{children}</>;
}

export default function App() {
  const { loading, user } = useAuth();
  if (loading) return <FullScreenLoader />;
  return (
    <Suspense fallback={<FullScreenLoader />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route path="/forgot-password" element={<Navigate to="/change-password" replace />} />
        <Route path="/reset-password" element={<Navigate to="/change-password" replace />} />
        <Route path="/app" element={<RequireAuth><AppLayout /></RequireAuth>}>
          <Route index element={<Navigate to={MODULES[0].path} replace />} />
          {modulesFor(!!user?.isAdmin).map((m) => <Route key={m.path} path={m.path} element={<m.component />} />)}
          <Route path="stock/:symbol" element={<StockDetailPage />} />
          <Route path="*" element={<div className="card"><EmptyState title="Page not found" body="This section doesn't exist." /></div>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
