import { Button, Popconfirm, Progress } from "@douyinfe/semi-ui";
import {
  Ban,
  ChevronDown,
  ChevronRight,
  Edit3,
  FolderKanban,
  FolderOpen,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRefreshWorkProjects } from "../../app/layouts/AdminLayout";
import { WORK_PROJECT_STATUS } from "../../shared/api/contract";
import {
  cancelWorkProject,
  createWorkProject,
  deleteWorkProject,
  queryWorkProjects,
  retryWorkProject,
  updateWorkProjectMetadata,
} from "../../shared/api/workProjects";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type {
  CreateWorkProjectRequest,
  WorkProject,
} from "../../shared/api/types";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { ResourceTable, type ResourceColumn } from "../../shared/components/ResourceTable";
import { ResourceIdentity, ResourceText, RowActions } from "../../shared/components/ResourceCells";
import { useAdminResourceHeader } from "../../shared/hooks/useAdminResourceHeader";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceSubmit } from "../../shared/hooks/useResourceSubmit";
import { formatDateTime } from "../../shared/lib/date";
import { UI_TEXT } from "../../shared/lib/uiText";
import { WorkProjectFormModal } from "./WorkProjectFormModal";
import {
  WorkProjectAssets,
  WorkProjectPanel,
  WorkProjectStatusTag,
  WorkProjectSummaries,
  WorkProjectTasks,
  WorkProjectTypeTag,
  workProjectOwnerNames,
} from "./workProjectView";

type AdminAction = "cancel" | "retry" | "delete";

export function WorkProjectsPage() {
  const {
    items: projects, page, keyword, loading, loadItems: loadProjects, total, rangeStart, rangeEnd,
    setKeyword, search, previous, next, canGoBack, canGoNext,
  } = usePagedResourceList<WorkProject>({ query: queryWorkProjects });
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<WorkProject | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const refreshProjectSidebar = useRefreshWorkProjects();
  const navigate = useNavigate();
  const [adminAction, setAdminAction] = useState<{ id: number; type: AdminAction } | null>(null);

  const refreshAll = useCallback(async () => {
    await loadProjects();
  }, [loadProjects]);

  useAdminResourceHeader({
    createLabel: "Create Project",
    refreshLabel: "Refresh work projects",
    loading,
    onCreate: () => {
      setEditingProject(null);
      setModalOpen(true);
    },
    onRefresh: refreshAll,
  });

  const { saving, submit } = useResourceSubmit({
    onSuccess: async () => {
      setModalOpen(false);
      setEditingProject(null);
      await refreshAll();
      refreshProjectSidebar();
    },
  });

  const summary = useMemo(
    () => projects.reduce(
      (acc, project) => ({
        working: acc.working + (project.status === WORK_PROJECT_STATUS.WORKING ? 1 : 0),
        sessions: acc.sessions + project.session_count,
        assets: acc.assets + project.assets.length,
      }),
      { working: 0, sessions: 0, assets: 0 },
    ),
    [projects],
  );

  const handleSubmit = (payload: CreateWorkProjectRequest) => submit(() => (
    editingProject
      ? updateWorkProjectMetadata(editingProject.id, payload)
      : createWorkProject(payload)
  ));

  const toggleProject = (project: WorkProject) => setExpandedId((current) => (
    current === project.id ? null : project.id
  ));

  const handleAdminProjectAction = async (
    project: WorkProject,
    type: AdminAction,
  ) => {
    setAdminAction({ id: project.id, type });
    try {
      const response = type === "cancel"
        ? await cancelWorkProject(project.id)
        : type === "retry"
          ? await retryWorkProject(project.id)
          : await deleteWorkProject(project.id);
      showApiSuccess(response);
      if (type === "delete") {
        setExpandedId((current) => (current === project.id ? null : current));
      }
      await loadProjects();
      refreshProjectSidebar();
    } catch (error) {
      showApiError(error);
    } finally {
      setAdminAction(null);
    }
  };

  const columns: ResourceColumn<WorkProject>[] = [
    {
      key: "project", header: "Project", width: "minmax(210px, 0.9fr)",
      render: (project) => (
        <ResourceIdentity
          before={(
            <Button
              icon={expandedId === project.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              theme="borderless"
              type="tertiary"
              size="small"
              onClick={() => toggleProject(project)}
              aria-label={`${expandedId === project.id ? "Collapse" : "Expand"} ${project.name}`}
            />
          )}
          icon={<FolderKanban size={18} />}
          title={project.name}
          detail={`${workProjectOwnerNames(project)} · ${project.session_count} sessions`}
        />
      ),
    },
    { key: "type", header: "Type", width: "132px", render: (project) => <WorkProjectTypeTag project={project} /> },
    { key: "status", header: "Status", width: "104px", render: (project) => <WorkProjectStatusTag project={project} /> },
    {
      key: "records", header: "Records", width: "minmax(170px, 0.5fr)",
      render: (project) => <ResourceText>{project.assets.length} assets · {project.tasks.length} tasks</ResourceText>,
    },
    { key: "updated", header: "Updated", width: "minmax(150px, 0.4fr)", render: (p) => formatDateTime(p.updated_at) },
    {
      key: "actions", header: "Actions", width: "132px",
      render: (project) => (
        <RowActions>
          <Button
            icon={<FolderOpen size={15} />}
            theme="borderless"
            type="tertiary"
            aria-label={`Open workspace for ${project.name}`}
            onClick={() => navigate(`/work-projects/${project.id}`)}
          />
          <Button
            icon={<Edit3 size={15} />}
            theme="borderless"
            type="tertiary"
            aria-label={`Edit ${project.name}`}
            onClick={() => { setEditingProject(project); setModalOpen(true); }}
          />
          <Button
            icon={<Ban size={15} />}
            theme="borderless"
            type="danger"
            disabled={!project.can_cancel}
            loading={adminAction?.id === project.id && adminAction.type === "cancel"}
            aria-label={`Cancel ${project.name}`}
            onClick={() => void handleAdminProjectAction(project, "cancel")}
          />
          <Button
            icon={<RotateCcw size={15} />}
            theme="borderless"
            type="tertiary"
            disabled={!project.can_retry}
            loading={adminAction?.id === project.id && adminAction.type === "retry"}
            aria-label={`Retry ${project.name}`}
            onClick={() => void handleAdminProjectAction(project, "retry")}
          />
          <Popconfirm title="Delete project" content={`Delete ${project.name} and all project sessions?`} okType="danger" cancelText={UI_TEXT.cancel} onConfirm={() => void handleAdminProjectAction(project, "delete")}>
            <Button
              icon={<Trash2 size={15} />}
              theme="borderless"
              type="danger"
              loading={adminAction?.id === project.id && adminAction.type === "delete"}
              aria-label={`Delete ${project.name}`}
            />
          </Popconfirm>
        </RowActions>
      ),
    },
  ];

  const expandedProject = projects.find((project) => project.id === expandedId) ?? null;

  return (
    <>
      <ResourcePageShell
        searchPlaceholder="Search project name, type, description, or status"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "Total", value: total },
          { label: "Working", value: summary.working },
          { label: "Project sessions", value: summary.sessions },
          { label: "Assets", value: summary.assets },
        ]}
        empty={projects.length === 0}
        emptyIcon={<FolderKanban size={42} />}
        emptyTitle="No projects found"
        page={page}
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        total={total}
        canGoBack={canGoBack}
        canGoNext={canGoNext}
        onKeywordChange={setKeyword}
        onSearch={search}
        onPrevious={previous}
        onNext={next}
      >
        <ResourceTable<WorkProject>
          ariaLabel="Work projects"
          className="work-projects-table"
          columns={columns}
          rows={projects}
          rowKey={(project) => project.id}
        />
        {expandedProject ? (
          <WorkProjectExpanded project={expandedProject} />
        ) : null}
      </ResourcePageShell>

      <WorkProjectFormModal
        open={modalOpen}
        saving={saving}
        project={editingProject}
        onCancel={() => { setModalOpen(false); setEditingProject(null); }}
        onSubmit={handleSubmit}
      />
    </>
  );
}

function WorkProjectExpanded({
  project,
}: {
  project: WorkProject;
}) {
  return (
    <div className="work-project-expanded">
      <section className="work-project-meta">
        <div>
          <span>Owner</span>
          <strong>{workProjectOwnerNames(project)}</strong>
        </div>
        <div>
          <span>Sandboxes</span>
          <strong>{project.sandbox_container_ids.length || "-"}</strong>
        </div>
        <div>
          <span>Task Progress</span>
          <Progress percent={project.progress} size="small" showInfo />
        </div>
      </section>

      <section className="work-project-detail-grid">
        <WorkProjectPanel title="Assets" empty={project.assets.length === 0 ? "No assets." : ""}>
          <WorkProjectAssets project={project} />
        </WorkProjectPanel>
        <WorkProjectPanel title="Tasks" empty={project.tasks.length === 0 ? "No tasks." : ""}>
          <WorkProjectTasks project={project} />
        </WorkProjectPanel>
        <WorkProjectPanel title="Agent Summaries" empty={project.agent_summaries.length === 0 ? "No summaries." : ""}>
          <WorkProjectSummaries project={project} />
        </WorkProjectPanel>
      </section>
    </div>
  );
}
