from enum import StrEnum

from pydantic import BaseModel


class ToolResultStatusSchema(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class ToolResultTypeSchema(StrEnum):
    SKILL_DETAIL = "skill_detail"
    KNOWLEDGE_DETAIL = "knowledge_detail"
    KNOWLEDGE_MUTATION = "knowledge_mutation"
    WORK_PROJECT = "work_project"


class ToolResultSchema(BaseModel):
    status: ToolResultStatusSchema
    type: ToolResultTypeSchema
    output: str = ""
