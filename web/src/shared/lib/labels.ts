import type { WorkProjectGraphEdgeCategory } from "../api/contract";
import {
  SANDBOX_CONTAINER_STATUSES,
  SYSTEM_USER_ROLES,
  WORK_PROJECT_ASSET_ORIGINS,
  WORK_PROJECT_ASSET_TYPES,
  WORK_PROJECT_ATTACK_PATH_STATUSES,
  WORK_PROJECT_FINDING_SEVERITIES,
  WORK_PROJECT_FINDING_STATUSES,
  WORK_PROJECT_GRAPH_EDGE_CATEGORIES,
  WORK_PROJECT_GRAPH_EDGE_TYPES,
  WORK_PROJECT_STATUSES,
  WORK_PROJECT_TASK_STATUSES,
  WORK_PROJECT_TYPES,
} from "../api/generated/constants";
import type {
  SandboxContainerStatus,
  SystemUserRole,
  WorkProjectAssetOrigin,
  WorkProjectAssetType,
  WorkProjectAttackPathStatus,
  WorkProjectFindingSeverity,
  WorkProjectFindingStatus,
  WorkProjectGraphEdgeType,
  WorkProjectStatus,
  WorkProjectTaskStatus,
  WorkProjectType,
} from "../api/types";

export type SemiTagColor = "amber" | "green" | "red" | "grey" | "blue" | "cyan";

export const SYSTEM_USER_ROLE_LABEL = labelsFromEnum<SystemUserRole>(SYSTEM_USER_ROLES);
export const WORK_PROJECT_TYPE_LABEL = labelsFromEnum<WorkProjectType>(WORK_PROJECT_TYPES, { source_code_audit: "Source Code Audit" });
export const WORK_PROJECT_STATUS_LABEL = labelsFromEnum<WorkProjectStatus>(WORK_PROJECT_STATUSES);
export const WORK_PROJECT_TASK_STATUS_LABEL = labelsFromEnum<WorkProjectTaskStatus>(WORK_PROJECT_TASK_STATUSES);
export const WORK_PROJECT_ASSET_TYPE_LABEL = labelsFromEnum<WorkProjectAssetType>(WORK_PROJECT_ASSET_TYPES);
export const WORK_PROJECT_ASSET_ORIGIN_LABEL = labelsFromEnum<WorkProjectAssetOrigin>(WORK_PROJECT_ASSET_ORIGINS);
export const WORK_PROJECT_FINDING_SEVERITY_LABEL = labelsFromEnum<WorkProjectFindingSeverity>(WORK_PROJECT_FINDING_SEVERITIES);
export const WORK_PROJECT_FINDING_STATUS_LABEL = labelsFromEnum<WorkProjectFindingStatus>(WORK_PROJECT_FINDING_STATUSES);
export const WORK_PROJECT_GRAPH_EDGE_TYPE_LABEL = labelsFromEnum<WorkProjectGraphEdgeType>(WORK_PROJECT_GRAPH_EDGE_TYPES);
export const WORK_PROJECT_GRAPH_EDGE_CATEGORY_LABEL = labelsFromEnum<WorkProjectGraphEdgeCategory>(WORK_PROJECT_GRAPH_EDGE_CATEGORIES);
export const WORK_PROJECT_ATTACK_PATH_STATUS_LABEL = labelsFromEnum<WorkProjectAttackPathStatus>(WORK_PROJECT_ATTACK_PATH_STATUSES);
export const SANDBOX_CONTAINER_STATUS_LABEL = labelsFromEnum<SandboxContainerStatus>(SANDBOX_CONTAINER_STATUSES);

export const SYSTEM_USER_ROLE_COLOR = colorsFromEnum<SystemUserRole>(SYSTEM_USER_ROLES, {
  admin: "red",
  user: "blue",
});

export const WORK_PROJECT_STATUS_COLOR = colorsFromEnum<WorkProjectStatus>(WORK_PROJECT_STATUSES, {
  working: "amber",
  completed: "green",
  canceled: "grey",
});

export const WORK_PROJECT_TYPE_COLOR = colorsFromEnum<WorkProjectType>(WORK_PROJECT_TYPES, {
  penetration_test: "blue",
  source_code_audit: "cyan",
});

export const WORK_PROJECT_TASK_STATUS_COLOR = colorsFromEnum<WorkProjectTaskStatus>(WORK_PROJECT_TASK_STATUSES, {
  todo: "grey",
  in_progress: "blue",
  blocked: "amber",
  done: "green",
});

export const WORK_PROJECT_FINDING_SEVERITY_COLOR = colorsFromEnum<WorkProjectFindingSeverity>(WORK_PROJECT_FINDING_SEVERITIES, {
  info: "grey",
  low: "blue",
  medium: "amber",
  high: "red",
  critical: "red",
});

export const WORK_PROJECT_FINDING_STATUS_COLOR = colorsFromEnum<WorkProjectFindingStatus>(WORK_PROJECT_FINDING_STATUSES, {
  suspected: "amber",
  validated: "red",
  false_positive: "grey",
});

export const WORK_PROJECT_ATTACK_PATH_STATUS_COLOR = colorsFromEnum<WorkProjectAttackPathStatus>(WORK_PROJECT_ATTACK_PATH_STATUSES, {
  suspected: "amber",
  validated: "red",
  blocked: "grey",
  closed: "green",
});

export const WORK_PROJECT_ASSET_ORIGIN_COLOR = colorsFromEnum<WorkProjectAssetOrigin>(WORK_PROJECT_ASSET_ORIGINS, {
  scope: "blue",
  discovered: "cyan",
});

export const WORK_PROJECT_GRAPH_EDGE_CATEGORY_COLOR = colorsFromEnum<WorkProjectGraphEdgeCategory>(WORK_PROJECT_GRAPH_EDGE_CATEGORIES, {
  structural: "blue",
  offensive: "red",
});

export const SANDBOX_CONTAINER_STATUS_COLOR = colorsFromEnum<SandboxContainerStatus>(SANDBOX_CONTAINER_STATUSES, {
  created: "blue",
  running: "green",
  stopped: "grey",
  error: "red",
});

function labelsFromEnum<T extends string>(
  values: readonly T[],
  overrides: Partial<Record<T, string>> = {},
): Record<T, string> {
  return Object.fromEntries(values.map((value) => [value, overrides[value] ?? titleCase(value)])) as Record<T, string>;
}

function colorsFromEnum<T extends string>(
  values: readonly T[],
  colors: Partial<Record<T, SemiTagColor>>,
): Record<T, SemiTagColor> {
  return Object.fromEntries(values.map((value) => [value, colors[value] ?? "grey"])) as Record<T, SemiTagColor>;
}

function titleCase(value: string): string {
  return value.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

// ── Blackboard labels (manual, not from generated schema) ──
export type BlackboardNodeType = "fact" | "intent" | "hint";
export type BlackboardNodeStatus = "proposed" | "in_progress" | "confirmed" | "rejected" | "superseded";

export const BLACKBOARD_NODE_TYPE_LABEL: Record<BlackboardNodeType, string> = {
  fact: "Fact",
  intent: "Intent",
  hint: "Hint",
};

export const BLACKBOARD_NODE_STATUS_LABEL: Record<BlackboardNodeStatus, string> = {
  proposed: "Proposed",
  in_progress: "In Progress",
  confirmed: "Confirmed",
  rejected: "Rejected",
  superseded: "Superseded",
};

export const BLACKBOARD_NODE_TYPE_COLOR: Record<BlackboardNodeType, SemiTagColor> = {
  fact: "green",
  intent: "blue",
  hint: "amber",
};

export const BLACKBOARD_NODE_STATUS_COLOR: Record<BlackboardNodeStatus, SemiTagColor> = {
  proposed: "grey",
  in_progress: "blue",
  confirmed: "green",
  rejected: "red",
  superseded: "amber",
};
