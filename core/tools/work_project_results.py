import json

from schema.common.tool_results import ToolResultSchema, ToolResultStatusSchema, ToolResultTypeSchema


def work_project_success(payload: object) -> str:
    return ToolResultSchema(
        status=ToolResultStatusSchema.SUCCESS,
        type=ToolResultTypeSchema.WORK_PROJECT,
        output=json.dumps(payload, ensure_ascii=False),
    ).model_dump_json()


def work_project_error(message: str) -> str:
    return ToolResultSchema(
        status=ToolResultStatusSchema.ERROR,
        type=ToolResultTypeSchema.WORK_PROJECT,
        output=message,
    ).model_dump_json()
