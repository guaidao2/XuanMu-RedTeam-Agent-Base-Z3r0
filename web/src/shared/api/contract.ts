import {
  SYSTEM_USER_ROLES,
  WORK_PROJECT_ASSET_ORIGIN,
  WORK_PROJECT_ASSET_TYPE,
  WORK_PROJECT_ASSET_TYPES,
  WORK_PROJECT_GRAPH_EDGE_CATEGORIES,
  WORK_PROJECT_GRAPH_EDGE_CATEGORY,
  WORK_PROJECT_STATUS,
  WORK_PROJECT_TYPES,
} from "./generated/constants";
import type {
  SystemUserRole,
  WorkProjectAssetType,
  WorkProjectGraphEdgeType,
  WorkProjectType,
} from "./types";

export {
  WORK_PROJECT_ASSET_ORIGIN,
  WORK_PROJECT_ASSET_TYPE,
  WORK_PROJECT_ASSET_TYPES,
  WORK_PROJECT_GRAPH_EDGE_CATEGORIES,
  WORK_PROJECT_STATUS,
};

export type WorkProjectGraphEdgeCategory = (typeof WORK_PROJECT_GRAPH_EDGE_CATEGORIES)[number];

export function workProjectEdgeCategory(type: WorkProjectGraphEdgeType): WorkProjectGraphEdgeCategory {
  return WORK_PROJECT_GRAPH_EDGE_CATEGORY[type];
}

const SYSTEM_USER_ROLE_SET = new Set<string>(SYSTEM_USER_ROLES);

const WORK_PROJECT_TYPE_SET = new Set<string>(WORK_PROJECT_TYPES);
const WORK_PROJECT_ASSET_TYPE_SET = new Set<string>(WORK_PROJECT_ASSET_TYPES);

export function getSystemUserRoles(): SystemUserRole[] {
  return [...SYSTEM_USER_ROLES];
}

export function isSystemUserRole(value: unknown): value is SystemUserRole {
  return typeof value === "string" && SYSTEM_USER_ROLE_SET.has(value);
}

export function getWorkProjectTypes(): WorkProjectType[] {
  return [...WORK_PROJECT_TYPES];
}

export function isWorkProjectType(value: unknown): value is WorkProjectType {
  return typeof value === "string" && WORK_PROJECT_TYPE_SET.has(value);
}

export function getWorkProjectAssetTypes(): WorkProjectAssetType[] {
  return [...WORK_PROJECT_ASSET_TYPES];
}

export function isWorkProjectAssetType(value: unknown): value is WorkProjectAssetType {
  return typeof value === "string" && WORK_PROJECT_ASSET_TYPE_SET.has(value);
}
