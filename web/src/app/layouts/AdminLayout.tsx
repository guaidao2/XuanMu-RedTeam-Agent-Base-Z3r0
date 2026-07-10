import { Avatar, Button } from "@douyinfe/semi-ui";
import { FolderKanban, LogOut, MessageSquareCode, Settings, Users } from "lucide-react";
import { ReactNode, Suspense, useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useOutletContext } from "react-router-dom";
import { SessionList } from "../../features/playground/SessionList";
import { useAgentSessionContext } from "../../features/playground/AgentSessionProvider";
import { useAuth } from "../../shared/auth/AuthProvider";
import { cx } from "../../shared/lib/className";
import xuanmuLogo from "../../assets/xuanmu-logo.svg";
import { preloadAdminRoute, preloadAdminRoutes } from "../routePreload";

type AdminLayoutContext = {
  setHeaderActions: (actions: ReactNode) => void;
  refreshWorkProjects: () => void;
};

export function useAdminHeaderActions() {
  return useOutletContext<AdminLayoutContext>().setHeaderActions;
}

export function useRefreshWorkProjects() {
  return useOutletContext<AdminLayoutContext>().refreshWorkProjects;
}

const navItems = [
  { path: "/playground", label: "Playground", eyebrow: "Agent Workbench", icon: MessageSquareCode },
  { path: "/work-projects", label: "Work Projects", eyebrow: "Project Operations", icon: FolderKanban, adminOnly: true },
  { path: "/system-users", label: "System Users", eyebrow: "Access Control", icon: Users, adminOnly: true },
  { path: "/system-config", label: "System Config", eyebrow: "Runtime Configuration", icon: Settings, adminOnly: true },
];

export function AdminLayout() {
  const { signOut, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [headerActions, setHeaderActionsState] = useState<ReactNode>(null);
  const [projectListVersion, setProjectListVersion] = useState(0);
  const {
    sessions,
    sessionsLoading,
    activeSessionId,
    selectSession,
    deleteSession,
    refreshSessions,
    dropSessionRuntime,
    syncSessionSummaries,
  } = useAgentSessionContext();

  const setHeaderActions = useCallback((actions: ReactNode) => {
    setHeaderActionsState(() => actions);
  }, []);

  useEffect(() => {
    const id = window.setTimeout(preloadAdminRoutes, 300);
    return () => window.clearTimeout(id);
  }, []);

  const refreshWorkProjects = useCallback(() => {
    setProjectListVersion((version) => version + 1);
  }, []);

  const handleSelectAgentSession = useCallback((sessionId: string) => {
    selectSession(sessionId);
    if (!location.pathname.startsWith("/playground")) {
      navigate("/playground");
    }
  }, [location.pathname, navigate, selectSession]);

  const outletContext: AdminLayoutContext = { setHeaderActions, refreshWorkProjects };

  const handleSignOut = () => {
    signOut();
    navigate("/login", { replace: true });
  };

  const isAdmin = user?.role === "admin";
  const visibleNavItems = navItems.filter((item) => !item.adminOnly || isAdmin);
  const activeItem = visibleNavItems.find((item) => location.pathname.startsWith(item.path));
  const contentMode = location.pathname.startsWith("/playground") ? "fixed" : "scroll";

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="brand-lockup">
          <img className="brand-logo" src={xuanmuLogo} alt="" />
          <div>
            <div className="brand-name">XuanMu</div>
            <div className="brand-kicker">红队智能体协作平台</div>
          </div>
        </div>

        <div className="admin-sidebar-body">
          <div className="admin-sidebar-top">
            <NavLink
              to="/playground"
              className="admin-nav-link"
              onFocus={() => preloadAdminRoute("/playground")}
              onPointerDown={() => preloadAdminRoute("/playground")}
              onPointerEnter={() => preloadAdminRoute("/playground")}
            >
              <MessageSquareCode size={18} />
              <span>Playground</span>
            </NavLink>
            <div className="admin-sidebar-secondary">
              <SessionList
                sessions={sessions}
                loading={sessionsLoading}
                activeSessionId={activeSessionId}
                projectListVersion={projectListVersion}
                onSelect={handleSelectAgentSession}
                onDelete={deleteSession}
                onRefreshSessions={refreshSessions}
                onDropRuntime={dropSessionRuntime}
                onSyncSessionSummaries={syncSessionSummaries}
              />
            </div>
          </div>

          <nav className="admin-nav admin-nav-bottom" aria-label="Primary navigation">
            {visibleNavItems.slice(1).map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className="admin-nav-link"
                  onFocus={() => preloadAdminRoute(item.path)}
                  onPointerDown={() => preloadAdminRoute(item.path)}
                  onPointerEnter={() => preloadAdminRoute(item.path)}
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>
        <div className="admin-sidebar-footer">
          <span className="brand-version">XuanMu v0.2.1</span>
          <span className="brand-fork">Based on <a href="https://github.com/yv1ing/Z3r0" target="_blank" rel="noopener noreferrer">Z3r0</a></span>
        </div>
      </aside>

      <div className="admin-main">
        <header className="admin-topbar">
          <div>
            <div className="page-eyebrow">{activeItem?.eyebrow || "Operations"}</div>
            <h1>{activeItem?.label || "Console"}</h1>
          </div>
          <div className="topbar-actions">
            {headerActions ? <div className="topbar-resource-actions">{headerActions}</div> : null}
            <div className="topbar-session-actions">
              <Avatar size="small" color="red">{user?.username?.[0]?.toUpperCase() || "U"}</Avatar>
              <Button icon={<LogOut size={16} />} theme="borderless" type="tertiary" onClick={handleSignOut} aria-label="Sign out" />
            </div>
          </div>
        </header>
        <main className="admin-content">
          <div className={cx("admin-content-viewport", `admin-content-viewport-${contentMode}`)}>
            <div className={cx("admin-route", `admin-route-${contentMode}`)}>
              <Suspense fallback={<AdminRouteFallback />}>
                <Outlet context={outletContext} />
              </Suspense>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function AdminRouteFallback() {
  return (
    <div className="admin-route-fallback">
      <div className="route-fallback-spinner" />
    </div>
  );
}
