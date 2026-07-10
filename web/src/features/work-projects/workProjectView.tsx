import { Progress, Tag } from "@douyinfe/semi-ui";
import { ClipboardList, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { WORK_PROJECT_ASSET_TYPE } from "../../shared/api/contract";
import type { WorkProject, WorkProjectAsset } from "../../shared/api/types";
import { formatDateTime } from "../../shared/lib/date";
import {
  WORK_PROJECT_ASSET_TYPE_LABEL,
  WORK_PROJECT_STATUS_COLOR,
  WORK_PROJECT_STATUS_LABEL,
  WORK_PROJECT_TASK_STATUS_COLOR,
  WORK_PROJECT_TASK_STATUS_LABEL,
  WORK_PROJECT_TYPE_COLOR,
  WORK_PROJECT_TYPE_LABEL,
} from "../../shared/lib/labels";

type WorkProjectViewMode = "expanded" | "info";

export function workProjectOwnerNames(project: WorkProject): string {
  return project.owners.map((owner) => owner.username).join(", ") || "No owners";
}

export function WorkProjectTypeTag({ project }: { project: WorkProject }) {
  return <Tag color={WORK_PROJECT_TYPE_COLOR[project.type]}>{WORK_PROJECT_TYPE_LABEL[project.type]}</Tag>;
}

export function WorkProjectStatusTag({ project }: { project: WorkProject }) {
  return <Tag color={WORK_PROJECT_STATUS_COLOR[project.status]}>{WORK_PROJECT_STATUS_LABEL[project.status]}</Tag>;
}

export function WorkProjectAssets({ project }: { project: WorkProject }) {
  return (
    <div className="work-project-asset-list">
      {project.assets.map((asset) => (
        <div key={asset.id}>
          <strong>{formatWorkProjectAsset(asset)}</strong>
          <span>{WORK_PROJECT_ASSET_TYPE_LABEL[asset.type]}</span>
        </div>
      ))}
    </div>
  );
}

export function formatWorkProjectAsset(asset: WorkProjectAsset): string {
  if (asset.type === WORK_PROJECT_ASSET_TYPE.BINARY) return asset.path || WORK_PROJECT_ASSET_TYPE_LABEL[asset.type];
  const host = asset.host || WORK_PROJECT_ASSET_TYPE_LABEL[asset.type];
  const port = asset.port ? `:${asset.port}` : "";
  return `${host}${port}`;
}

export function WorkProjectTasks({
  project,
  mode = "expanded",
}: {
  project: WorkProject;
  mode?: WorkProjectViewMode;
}) {
  const listClassName = mode === "info" ? "project-info-scroll-list" : "work-project-task-list";
  const rowClassName = mode === "info" ? "project-info-task-row" : "work-project-task-row";
  const showIcon = mode === "expanded";
  return (
    <div className={listClassName}>
      {project.tasks.map((task) => (
        <div key={task.id ?? task.title} className={rowClassName}>
          {showIcon ? <ClipboardList size={14} /> : null}
          <span className="work-project-task-title">{task.title}</span>
          <Tag color={WORK_PROJECT_TASK_STATUS_COLOR[task.status]}>{WORK_PROJECT_TASK_STATUS_LABEL[task.status]}</Tag>
          <Progress percent={task.progress} size="small" showInfo={false} />
        </div>
      ))}
    </div>
  );
}

export function WorkProjectSummaries({
  project,
  mode = "expanded",
}: {
  project: WorkProject;
  mode?: WorkProjectViewMode;
}) {
  const listClassName = mode === "info" ? "project-info-scroll-list" : "work-project-summary-list";
  const rowClassName = mode === "info" ? "project-info-summary" : "work-project-summary-row";
  const progressClassName = mode === "info" ? "project-info-summary-task" : "work-project-summary-progress";
  const blockClassName = mode === "info" ? "project-info-summary-block" : "work-project-summary-block";
  const showIcon = mode === "expanded";
  return (
    <div className={listClassName}>
      {project.agent_summaries.map((summary) => (
        <article key={summary.agent_code} className={rowClassName}>
          <header>
            {showIcon ? <UserRound size={14} /> : null}
            <strong>{summary.agent_code}</strong>
            {summary.updated_at ? <span>{formatDateTime(summary.updated_at)}</span> : null}
          </header>
          {summary.summary?.task_id || summary.summary?.task_title ? (
            <div className={progressClassName}>
              <span>{summary.summary.task_id || summary.summary.task_title}</span>
              <Progress percent={summary.summary.progress ?? 0} size="small" showInfo />
            </div>
          ) : null}
          <SummaryBlock className={blockClassName} label="Status" value={summary.summary?.status} />
          <SummaryList className={blockClassName} label="Findings" values={summary.summary?.findings ?? []} />
          <SummaryList className={blockClassName} label="Decisions" values={summary.summary?.decisions ?? []} />
          <SummaryList className={blockClassName} label="Blockers" values={summary.summary?.blockers ?? []} />
          <SummaryList className={blockClassName} label="Next Steps" values={summary.summary?.next_steps ?? []} />
          <SummaryBlock className={blockClassName} label="Notes" value={summary.summary?.notes} />
        </article>
      ))}
    </div>
  );
}

export function WorkProjectPanel({
  title,
  empty,
  mode = "expanded",
  icon,
  children,
}: {
  title: string;
  empty: string;
  mode?: WorkProjectViewMode;
  icon?: ReactNode;
  children: ReactNode;
}) {
  const className = mode === "info" ? "project-info-panel" : "work-project-panel";
  const emptyClassName = mode === "info" ? "project-info-empty" : "work-project-panel-empty";
  return (
    <section className={className}>
      <header>
        {icon}
        <strong>{title}</strong>
      </header>
      {empty ? <div className={emptyClassName}>{empty}</div> : children}
    </section>
  );
}

function SummaryBlock({ className, label, value }: { className: string; label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className={className}>
      <span>{label}</span>
      <p>{value}</p>
    </div>
  );
}

function SummaryList({ className, label, values }: { className: string; label: string; values: string[] }) {
  if (!values.length) return null;
  return (
    <div className={className}>
      <span>{label}</span>
      <ul>
        {values.map((value, index) => <li key={`${index}:${value}`}>{value}</li>)}
      </ul>
    </div>
  );
}
