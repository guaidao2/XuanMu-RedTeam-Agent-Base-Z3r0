from schema.work_project.projects import WorkProjectStatus, WorkProjectTaskSchema, WorkProjectTaskStatus


def calculate_work_project_progress(tasks: list[dict] | list[WorkProjectTaskSchema]) -> float:
    if not tasks:
        return 0
    progress_values = [
        WorkProjectTaskSchema.model_validate(task).progress
        for task in tasks
    ]
    return round(sum(progress_values) / len(progress_values), 2)


def derive_work_project_status(
    tasks: list[dict] | list[WorkProjectTaskSchema],
    current_status: WorkProjectStatus,
) -> WorkProjectStatus:
    if current_status == WorkProjectStatus.CANCELED:
        return WorkProjectStatus.CANCELED
    if not tasks:
        return WorkProjectStatus.WORKING

    statuses = [
        WorkProjectTaskSchema.model_validate(task).status
        for task in tasks
    ]
    if all(status == WorkProjectTaskStatus.DONE for status in statuses):
        return WorkProjectStatus.COMPLETED
    return WorkProjectStatus.WORKING
