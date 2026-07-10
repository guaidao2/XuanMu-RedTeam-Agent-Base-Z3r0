import { ContainerShellProvider } from "../../features/container-shell/ContainerShellProvider";
import { AgentSessionProvider } from "../../features/playground/AgentSessionProvider";
import { AdminLayout } from "./AdminLayout";

export function ProtectedAdminShell() {
  return (
    <div className="admin-app">
      <AgentSessionProvider>
        <ContainerShellProvider>
          <AdminLayout />
        </ContainerShellProvider>
      </AgentSessionProvider>
    </div>
  );
}
