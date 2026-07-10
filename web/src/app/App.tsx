import { lazy, Suspense, type ComponentType } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation, useOutletContext } from "react-router-dom";
import { AuthProvider, useAuth } from "../shared/auth/AuthProvider";
import {
  loadLandingPage,
  loadLoginPage,
  loadPlaygroundPage,
  loadProtectedAdminShell,
  loadSystemConfigPage,
  loadSystemUsersPage,
  loadWorkProjectWorkspacePage,
  loadWorkProjectsPage,
} from "./routePreload";

function lazyRoute<TModule extends Record<TKey, ComponentType>, TKey extends keyof TModule>(
  loader: () => Promise<TModule>,
  key: TKey,
) {
  return lazy(() => loader().then((module) => ({ default: module[key] })));
}

const LandingPage = lazyRoute(loadLandingPage, "LandingPage");
const LoginPage = lazyRoute(loadLoginPage, "LoginPage");
const ProtectedAdminShell = lazyRoute(loadProtectedAdminShell, "ProtectedAdminShell");
const PlaygroundPage = lazyRoute(loadPlaygroundPage, "PlaygroundPage");
const WorkProjectWorkspacePage = lazyRoute(loadWorkProjectWorkspacePage, "WorkProjectWorkspacePage");
const SystemUsersPage = lazyRoute(loadSystemUsersPage, "SystemUsersPage");
const SystemConfigPage = lazyRoute(loadSystemConfigPage, "SystemConfigPage");
const WorkProjectsPage = lazyRoute(loadWorkProjectsPage, "WorkProjectsPage");

function ProtectedRoute() {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}

function AdminOnlyRoute() {
  const { user } = useAuth();
  const outletContext = useOutletContext();
  if (user?.role !== "admin") {
    return <Navigate to="/playground" replace />;
  }
  return <Outlet context={outletContext} />;
}

function PublicOnlyRoute() {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) {
    return <Navigate to="/playground" replace />;
  }
  return <Outlet />;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route element={<PublicOnlyRoute />}>
              <Route path="/login" element={<LoginPage />} />
            </Route>
            <Route element={<ProtectedRoute />}>
              <Route element={<ProtectedAdminShell />}>
                <Route path="/playground" element={<PlaygroundPage />} />
                <Route element={<AdminOnlyRoute />}>
                  <Route path="/work-projects" element={<WorkProjectsPage />} />
                  <Route path="/work-projects/:projectId" element={<WorkProjectWorkspacePage />} />
                  <Route path="/system-users" element={<SystemUsersPage />} />
                  <Route path="/system-config" element={<SystemConfigPage />} />
                </Route>
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/playground" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  );
}

function RouteFallback() {
  return (
    <div className="route-fallback">
      <div className="route-fallback-spinner" />
    </div>
  );
}
