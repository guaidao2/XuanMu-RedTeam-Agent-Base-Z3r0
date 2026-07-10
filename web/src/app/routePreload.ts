const routeLoaders = {
  landing: () => import("../features/landing/LandingPage"),
  login: () => import("../features/auth/LoginPage"),
  protectedAdminShell: () => import("./layouts/ProtectedAdminShell"),
  egressProxies: () => import("../features/egress-proxies/EgressProxiesPage"),
  hosts: () => import("../features/hosts/HostsPage"),
  playground: () => import("../features/playground/PlaygroundPage"),
  workProjects: () => import("../features/work-projects/WorkProjectsPage"),
  workProjectWorkspace: () => import("../features/work-projects/WorkProjectWorkspacePage"),
  sandboxImages: () => import("../features/sandbox-images/SandboxImagesPage"),
  sandboxContainers: () => import("../features/sandbox-containers/SandboxContainersPage"),
  systemUsers: () => import("../features/system-users/SystemUsersPage"),
  systemConfig: () => import("../features/system-config/SystemConfigPage"),
} as const;

const adminRouteLoaders: Record<string, () => Promise<unknown>> = {
  "/playground": routeLoaders.playground,
  "/egress-proxies": routeLoaders.egressProxies,
  "/hosts": routeLoaders.hosts,
  "/work-projects": routeLoaders.workProjects,
  "/work-projects/:projectId": routeLoaders.workProjectWorkspace,
  "/sandbox-images": routeLoaders.sandboxImages,
  "/sandbox-containers": routeLoaders.sandboxContainers,
  "/system-users": routeLoaders.systemUsers,
  "/system-config": routeLoaders.systemConfig,
};

const preloadedRoutes = new Set<string>();

export const loadLandingPage = routeLoaders.landing;
export const loadLoginPage = routeLoaders.login;
export const loadProtectedAdminShell = routeLoaders.protectedAdminShell;
export const loadEgressProxiesPage = routeLoaders.egressProxies;
export const loadHostsPage = routeLoaders.hosts;
export const loadPlaygroundPage = routeLoaders.playground;
export const loadWorkProjectsPage = routeLoaders.workProjects;
export const loadWorkProjectWorkspacePage = routeLoaders.workProjectWorkspace;
export const loadSandboxImagesPage = routeLoaders.sandboxImages;
export const loadSandboxContainersPage = routeLoaders.sandboxContainers;
export const loadSystemUsersPage = routeLoaders.systemUsers;
export const loadSystemConfigPage = routeLoaders.systemConfig;

export function preloadAdminRoute(path: string) {
  const loader = adminRouteLoaders[path];
  if (!loader || preloadedRoutes.has(path)) return;
  preloadedRoutes.add(path);
  void loader().catch(() => preloadedRoutes.delete(path));
}

export function preloadAdminRoutes() {
  for (const path of Object.keys(adminRouteLoaders)) {
    preloadAdminRoute(path);
  }
}
