import { Button, Empty, Spin } from "@douyinfe/semi-ui";
import { ArrowLeft, FileText } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MetricStrip } from "../../shared/components/ResourcePageShell";
import { WorkProjectRecordTabs } from "./ProjectRecordViews";
import { useWorkProjectRecordSnapshot } from "./workProjectRecords";
import { workProjectOwnerNames, WorkProjectStatusTag, WorkProjectTypeTag } from "./workProjectView";

export function WorkProjectWorkspacePage() {
  const params = useParams();
  const navigate = useNavigate();
  const projectId = Number(params.projectId);
  const validProjectId = Number.isFinite(projectId) && projectId > 0 ? projectId : null;
  const { project, records, loading } = useWorkProjectRecordSnapshot(validProjectId);

  const metrics = useMemo(() => [
    { label: "Assets", value: records.assets.length },
    { label: "Findings", value: records.findings.length },
    { label: "Relationships", value: records.graph.edges.length },
    { label: "Sessions", value: project?.session_count ?? 0 },
  ], [project, records]);

  if (!validProjectId) {
    return <Empty className="empty-state" image={<FileText size={42} />} title="Invalid project" description="" />;
  }

  return (
    <section className="work-project-workspace">
      <div className="workspace-back-row">
        <Button icon={<ArrowLeft size={15} />} theme="borderless" type="tertiary" onClick={() => navigate("/work-projects")}>
          Back
        </Button>
      </div>
      <div className="workspace-header">
        {project ? (
          <div className="workspace-title">
            <div className="workspace-title-main">
              <h2>{project.name}</h2>
              {project.description ? <p>{project.description}</p> : null}
              <span>Owners: {workProjectOwnerNames(project)}</span>
            </div>
            <div className="workspace-title-tags">
              <WorkProjectTypeTag project={project} />
              <WorkProjectStatusTag project={project} />
            </div>
          </div>
        ) : null}
      </div>

      <MetricStrip metrics={metrics} />

      <Spin spinning={loading}>
        <WorkProjectRecordTabs records={records} className="workspace-tabs" />
      </Spin>
    </section>
  );
}
