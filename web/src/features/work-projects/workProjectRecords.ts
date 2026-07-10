import { useEffect, useState } from "react";
import { showApiError } from "../../shared/api/feedback";
import { getWorkProjectRecordSnapshot } from "../../shared/api/workProjects";
import type { WorkProject, WorkProjectGraphSnapshot, WorkProjectRecordSnapshot, WorkProjectRecords } from "../../shared/api/types";

export type WorkProjectSnapshotState = {
  project: WorkProject | null;
  records: WorkProjectRecords;
  loading: boolean;
};

export const EMPTY_WORK_PROJECT_GRAPH: WorkProjectGraphSnapshot = {
  edges: [],
  attack_paths: [],
  attack_path_steps: [],
};

export const EMPTY_WORK_PROJECT_RECORDS: WorkProjectRecords = {
  assets: [],
  findings: [],
  graph: EMPTY_WORK_PROJECT_GRAPH,
};

export async function loadWorkProjectRecordSnapshot(projectId: number): Promise<WorkProjectRecordSnapshot> {
  const response = await getWorkProjectRecordSnapshot(projectId);
  if (!response.data) throw new Error("Work project snapshot is empty");
  return response.data;
}

export function useWorkProjectRecordSnapshot(projectId: number | null, enabled = true): WorkProjectSnapshotState {
  const [state, setState] = useState<WorkProjectSnapshotState>({
    project: null,
    records: EMPTY_WORK_PROJECT_RECORDS,
    loading: false,
  });

  useEffect(() => {
    let canceled = false;
    if (!enabled || !projectId) {
      setState({ project: null, records: EMPTY_WORK_PROJECT_RECORDS, loading: false });
      return () => {
        canceled = true;
      };
    }

    setState({ project: null, records: EMPTY_WORK_PROJECT_RECORDS, loading: true });
    loadWorkProjectRecordSnapshot(projectId)
      .then((snapshot) => {
        if (!canceled) setState({ project: snapshot.project, records: snapshot.records, loading: false });
      })
      .catch((error) => {
        if (!canceled) {
          showApiError(error);
          setState({ project: null, records: EMPTY_WORK_PROJECT_RECORDS, loading: false });
        }
      });

    return () => {
      canceled = true;
    };
  }, [enabled, projectId]);

  return state;
}

export type { WorkProjectRecordSnapshot, WorkProjectRecords };
