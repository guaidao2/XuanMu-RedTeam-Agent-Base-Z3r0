import { Button, Input, Modal, Popconfirm, Spin } from "@douyinfe/semi-ui";
import { ChevronDown, ChevronRight, Edit3, FolderKanban, Info, MessageCircle, MessageSquarePlus, Play, Trash2 } from "lucide-react";
import { ReactNode, useCallback, useEffect, useState } from "react";
import { updateAgentSessionTitle } from "../../shared/api/agentSessions";
import { showApiError } from "../../shared/api/feedback";
import {
  createWorkProjectSession,
  deleteWorkProjectSession,
  listWorkProjectSessions,
  queryWorkProjects,
} from "../../shared/api/workProjects";
import type { AgentSessionSummary, WorkProject } from "../../shared/api/types";
import { useResourceSubmit } from "../../shared/hooks/useResourceSubmit";
import { cx } from "../../shared/lib/className";
import { UI_TEXT } from "../../shared/lib/uiText";
import { WorkProjectInfoModal } from "../work-projects/WorkProjectInfoModal";

const PROJECT_REFRESH_INTERVAL_MS = 5000;

type SessionListProps = {
  sessions: AgentSessionSummary[];
  loading: boolean;
  activeSessionId: string | null;
  projectListVersion: number;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  onRefreshSessions: () => Promise<void>;
  onDropRuntime: (sessionId: string) => void;
  onSyncSessionSummaries: (items: AgentSessionSummary[]) => void;
};

type ProjectSessionState = {
  loading: boolean;
  items: AgentSessionSummary[];
};

type ChatSessionRowProps = {
  session: AgentSessionSummary;
  active: boolean;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  onRename: (session: AgentSessionSummary) => void;
};

type SessionRowProps = {
  active: boolean;
  className?: string;
  deleteConfirm?: {
    title: string;
    content: string;
    onConfirm: () => void;
  };
  icon: ReactNode;
  session: AgentSessionSummary;
  titleFallback: string;
  onRename: () => void;
  onSelect: () => void;
};

type ProjectGroupProps = {
  project: WorkProject;
  state?: ProjectSessionState;
  expanded: boolean;
  activeSessionId: string | null;
  onToggle: (projectId: number) => void;
  onShowInfo: (project: WorkProject) => void;
  onCreateSession: (project: WorkProject) => void;
  onSelectSession: (sessionId: string) => void;
  onRenameSession: (session: AgentSessionSummary, projectId: number) => void;
  onDeleteSession: (projectId: number, sessionId: string) => void;
};

type RenameTarget = {
  session: AgentSessionSummary;
  projectId?: number;
};

export function SessionList({
  sessions,
  loading,
  activeSessionId,
  projectListVersion,
  onSelect,
  onDelete,
  onRefreshSessions,
  onDropRuntime,
  onSyncSessionSummaries,
}: SessionListProps) {
  const [projects, setProjects] = useState<WorkProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [expandedProjectId, setExpandedProjectId] = useState<number | null>(null);
  const [projectSessions, setProjectSessions] = useState<Map<number, ProjectSessionState>>(() => new Map());
  const [infoOpen, setInfoOpen] = useState(false);
  const [infoProjectId, setInfoProjectId] = useState<number | null>(null);
  const [renameTarget, setRenameTarget] = useState<RenameTarget | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const { saving: renaming, submit } = useResourceSubmit();

  const loadProjects = useCallback(async (silent = false) => {
    if (!silent) setProjectsLoading(true);
    try {
      const response = await queryWorkProjects({ page: 1, size: 100, keyword: "" });
      setProjects(response.data?.items ?? []);
    } catch (error) {
      if (!silent) showApiError(error);
    } finally {
      if (!silent) setProjectsLoading(false);
    }
  }, []);

  const loadProjectSessions = useCallback(async (projectId: number, silent = false) => {
    if (!silent) {
      setProjectSessions((prev) => new Map(prev).set(projectId, {
        loading: true,
        items: prev.get(projectId)?.items ?? [],
      }));
    }
    try {
      const response = await listWorkProjectSessions(projectId);
      const items = response.data?.items ?? [];
      setProjectSessions((prev) => new Map(prev).set(projectId, {
        loading: false,
        items,
      }));
      onSyncSessionSummaries(items);
    } catch (error) {
      if (!silent) showApiError(error);
      if (!silent) {
        setProjectSessions((prev) => new Map(prev).set(projectId, {
          loading: false,
          items: prev.get(projectId)?.items ?? [],
        }));
      }
    }
  }, [onSyncSessionSummaries]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects, projectListVersion]);

  useEffect(() => {
    for (const project of projects) {
      if (!projectSessions.has(project.id)) {
        void loadProjectSessions(project.id, true);
      }
    }
  }, [loadProjectSessions, projectSessions, projects]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadProjects(true);
      for (const project of projects) {
        void loadProjectSessions(project.id, true);
      }
    }, PROJECT_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loadProjectSessions, loadProjects, projects]);

  const toggleProject = (projectId: number) => {
    const nextProjectId = expandedProjectId === projectId ? null : projectId;
    setExpandedProjectId(nextProjectId);
    if (nextProjectId) void loadProjectSessions(nextProjectId);
  };

  const createProjectSession = async (project: WorkProject) => {
    await submit(async () => {
      const response = await createWorkProjectSession(project.id);
      const sessionId = response.data?.session_id;
      if (!sessionId) return response;
      await loadProjectSessions(project.id);
      onSelect(sessionId);
      return response;
    });
  };

  const deleteProjectSession = async (projectId: number, sessionId: string) => {
    await submit(async () => {
      const response = await deleteWorkProjectSession(projectId, sessionId);
      onDropRuntime(sessionId);
      await loadProjectSessions(projectId);
      return response;
    });
  };

  const openRename = (target: RenameTarget) => {
    setRenameTarget(target);
    setRenameTitle(target.session.title || "");
  };

  const saveRename = async () => {
    const title = renameTitle.trim();
    if (!renameTarget || !title) return;
    await submit(async () => {
      const response = await updateAgentSessionTitle(renameTarget.session.session_id, { title });
      setRenameTarget(null);
      setRenameTitle("");
      if (renameTarget.projectId) {
        await loadProjectSessions(renameTarget.projectId, true);
      } else {
        await onRefreshSessions();
      }
      return response;
    });
  };

  const showProjectInfo = (project: WorkProject) => {
    setInfoProjectId(project.id);
    setInfoOpen(true);
  };

  const empty = sessions.length === 0 && projects.length === 0 && !loading && !projectsLoading;

  return (
    <div className="session-list">
      <div className="session-list-body">
        <Spin spinning={loading || projectsLoading} wrapperClassName="session-list-spin">
          {empty ? (
            <div className="session-empty">
              <MessageCircle size={28} />
              <p>No conversations yet.</p>
            </div>
          ) : (
            <>
              {sessions.map((session) => (
                <ChatSessionRow
                  key={session.session_id}
                  session={session}
                  active={session.session_id === activeSessionId}
                  onSelect={onSelect}
                  onDelete={onDelete}
                  onRename={(targetSession) => openRename({ session: targetSession })}
                />
              ))}
              {projects.map((project) => (
                <ProjectGroup
                  key={project.id}
                  project={project}
                  state={projectSessions.get(project.id)}
                  expanded={expandedProjectId === project.id}
                  activeSessionId={activeSessionId}
                  onToggle={toggleProject}
                  onShowInfo={showProjectInfo}
                  onCreateSession={(targetProject) => void createProjectSession(targetProject)}
                  onSelectSession={onSelect}
                  onRenameSession={(targetSession, projectId) => openRename({ session: targetSession, projectId })}
                  onDeleteSession={(projectId, sessionId) => void deleteProjectSession(projectId, sessionId)}
                />
              ))}
            </>
          )}
        </Spin>
      </div>
      <WorkProjectInfoModal
        open={infoOpen}
        projectId={infoProjectId}
        onClose={() => {
          setInfoOpen(false);
          setInfoProjectId(null);
        }}
      />
      <Modal
        visible={Boolean(renameTarget)}
        title="Edit Session Title"
        okText={UI_TEXT.save}
        cancelText={UI_TEXT.cancel}
        confirmLoading={renaming}
        okButtonProps={{ type: "primary", disabled: !renameTitle.trim() }}
        onOk={() => void saveRename()}
        onCancel={() => setRenameTarget(null)}
      >
        <Input
          autoFocus
          maxLength={80}
          value={renameTitle}
          onChange={setRenameTitle}
          onEnterPress={() => void saveRename()}
        />
      </Modal>
    </div>
  );
}

function ChatSessionRow({ session, active, onSelect, onDelete, onRename }: ChatSessionRowProps) {
  return (
    <SessionRow
      active={active}
      deleteConfirm={{
        title: "Delete chat",
        content: "Permanently delete this conversation?",
        onConfirm: () => onDelete(session.session_id),
      }}
      icon={<MessageCircle size={14} />}
      session={session}
      titleFallback="Untitled session"
      onRename={() => onRename(session)}
      onSelect={() => onSelect(session.session_id)}
    />
  );
}

function ProjectGroup({
  project,
  state,
  expanded,
  activeSessionId,
  onToggle,
  onShowInfo,
  onCreateSession,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
}: ProjectGroupProps) {
  return (
    <div className="session-project-group">
      <div className="session-row session-row-project">
        <button type="button" className="session-row-main" onClick={() => onToggle(project.id)}>
          <span className="session-row-icon">
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
          <span className="session-row-body">
            <span className="session-row-title">{project.name}</span>
          </span>
        </button>
        <Button
          icon={<Info size={14} />}
          theme="borderless"
          type="tertiary"
          size="small"
          aria-label={`View ${project.name} details`}
          onClick={() => onShowInfo(project)}
        />
        <Button
          icon={<MessageSquarePlus size={14} />}
          theme="borderless"
          type="primary"
          size="small"
          disabled={!project.can_create_session}
          aria-label={`Create session for ${project.name}`}
          onClick={() => onCreateSession(project)}
        />
      </div>

      {expanded ? (
        <div className="session-project-children">
          {state?.loading ? <div className="session-project-empty">Loading sessions...</div> : null}
          {!state?.loading && (!state || state.items.length === 0) ? (
            <button
              type="button"
              className="session-project-empty"
              disabled={!project.can_create_session}
              onClick={() => onCreateSession(project)}
            >
              <FolderKanban size={14} />
              <span>New project session</span>
            </button>
          ) : null}
          {state?.items.map((session) => (
            <ProjectSessionRow
              key={session.session_id}
              session={session}
              projectId={project.id}
              active={session.session_id === activeSessionId}
              onSelect={onSelectSession}
              onRename={onRenameSession}
              onDelete={onDeleteSession}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ProjectSessionRow({
  session,
  projectId,
  active,
  onSelect,
  onRename,
  onDelete,
}: {
  session: AgentSessionSummary;
  projectId: number;
  active: boolean;
  onSelect: (sessionId: string) => void;
  onRename: (session: AgentSessionSummary, projectId: number) => void;
  onDelete: (projectId: number, sessionId: string) => void;
}) {
  return (
    <SessionRow
      active={active}
      className="session-row-project-session"
      deleteConfirm={{
        title: "Delete session",
        content: "Permanently delete this project session?",
        onConfirm: () => onDelete(projectId, session.session_id),
      }}
      icon={<Play size={13} />}
      session={session}
      titleFallback="Project session"
      onRename={() => onRename(session, projectId)}
      onSelect={() => onSelect(session.session_id)}
    />
  );
}

function SessionRow({
  active,
  className,
  deleteConfirm,
  icon,
  session,
  titleFallback,
  onRename,
  onSelect,
}: SessionRowProps) {
  const title = session.title || titleFallback;
  const rowClassName = cx("session-row", className, active && "session-row-active");
  const deleteButton = (
    <Button
      icon={<Trash2 size={14} />}
      theme="borderless"
      type="danger"
      size="small"
      aria-label={`Delete ${session.title || session.session_id}`}
    />
  );

  return (
    <div className={rowClassName}>
      <button type="button" className="session-row-main" onClick={onSelect}>
        <span className="session-row-icon">{icon}</span>
        <span className="session-row-body">
          <span className="session-row-title">{title}</span>
        </span>
      </button>
      <Button
        icon={<Edit3 size={14} />}
        theme="borderless"
        type="tertiary"
        size="small"
        aria-label={`Edit ${session.title || session.session_id}`}
        onClick={onRename}
      />
      {deleteConfirm ? (
        <Popconfirm {...deleteConfirm} okType="danger" cancelText={UI_TEXT.cancel}>
          {deleteButton}
        </Popconfirm>
      ) : null}
    </div>
  );
}
