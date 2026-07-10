from pydantic import BaseModel

from schema.work_project.assets import WorkProjectAssetSchema
from schema.work_project.findings import WorkProjectFindingSchema
from schema.work_project.graph import WorkProjectGraphSnapshotSchema
from schema.work_project.projects import WorkProjectSchema


class WorkProjectRecordsSchema(BaseModel):
    assets: list[WorkProjectAssetSchema]
    findings: list[WorkProjectFindingSchema]
    graph: WorkProjectGraphSnapshotSchema


class WorkProjectRecordSnapshotSchema(BaseModel):
    project: WorkProjectSchema
    records: WorkProjectRecordsSchema
