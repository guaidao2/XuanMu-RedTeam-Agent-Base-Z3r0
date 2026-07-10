import { Empty, Modal, Progress, Spin } from "@douyinfe/semi-ui";
import { FileText, UserRound } from "lucide-react";
import type { WorkProject } from "../../shared/api/types";
import { type ProjectRecordTab, WorkProjectRecordTabs } from "./ProjectRecordViews";
import { useWorkProjectRecordSnapshot } from "./workProjectRecords";
import {
  WorkProjectPanel,
  WorkProjectStatusTag,
  WorkProjectSummaries,
  WorkProjectTasks,
  WorkProjectTypeTag,
  workProjectOwnerNames,
} from "./workProjectView";

type WorkProjectInfoModalProps = {
  open: boolean;
  projectId: number | null;
  initialTab?: ProjectRecordTab;
  onClose: () => void;
};

export function WorkProjectInfoModal({ open, projectId, initialTab = "assets", onClose }: WorkProjectInfoModalProps) {
  const { project, records, loading } = useWorkProjectRecordSnapshot(projectId, open);

  return (
    <Modal
      visible={open}
      title={<ProjectInfoTitle project={project} />}
      width="min(1440px, calc(100vw - 24px))"
      footer={null}
      onCancel={onClose}
    >
      <Spin spinning={loading}>
        {project ? (
          <div className="project-info-content project-record-content">
            <section className="project-info-main">
              <section className="project-info-meta">
                <div>
                  <span>Type</span>
                  <WorkProjectTypeTag project={project} />
                </div>
                <div>
                  <span>Status</span>
                  <WorkProjectStatusTag project={project} />
                </div>
                <div>
                  <span>Owners</span>
                  <strong>{workProjectOwnerNames(project)}</strong>
                </div>
                <div>
                  <span>Sandbox</span>
                  <strong>{project.sandbox_container_ids.length || "-"}</strong>
                </div>
              </section>

              {project.description ? <div className="project-info-description">{project.description}</div> : null}

              <section className="project-info-progress">
                <span>Task Progress</span>
                <Progress percent={project.progress} size="small" showInfo />
              </section>

              <WorkProjectPanel
                title="Tasks"
                icon={<FileText size={15} />}
                empty={!project.tasks.length ? "No data." : ""}
                mode="info"
              >
                <WorkProjectTasks project={project} mode="info" />
              </WorkProjectPanel>

              <WorkProjectPanel
                title="Agent Summaries"
                icon={<UserRound size={15} />}
                empty={!project.agent_summaries.length ? "No data." : ""}
                mode="info"
              >
                <WorkProjectSummaries project={project} mode="info" />
              </WorkProjectPanel>
            </section>

            <section className="project-record-panel">
              <WorkProjectRecordTabs
                records={records}
                initialTab={initialTab}
              />
            </section>
          </div>
        ) : (
          <Empty className="empty-state" image={<FileText size={42} />} title="No project selected." description="" />
        )}
      </Spin>
    </Modal>
  );
}

function ProjectInfoTitle({ project }: { project: WorkProject | null }) {
  return (
    <div className="project-info-title">
      <strong>{project?.name ?? "Work Project"}</strong>
    </div>
  );
}
