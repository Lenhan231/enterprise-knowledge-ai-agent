"""Small, validated plans for document and SQL orchestration."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str = Field(min_length=1, max_length=32)
    kind: Literal['rows', 'evidence']
    field: str | None = Field(default=None, max_length=80)


class AgentTask(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,32}$')
    agent: Literal['knowledge', 'sql']
    question: str = Field(min_length=1, max_length=2000)
    depends_on: list[str] = Field(default_factory=list, max_length=3)
    inputs: list[TaskInput] = Field(default_factory=list, max_length=3)


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    objective: str = Field(min_length=1, max_length=2000)
    tasks: list[AgentTask] = Field(default_factory=list, max_length=4)
    clarification: str | None = Field(default=None, min_length=1, max_length=500)
    fallback: bool = False

    @model_validator(mode='after')
    def validate_dependencies(self):
        if bool(self.tasks) == bool(self.clarification):
            raise ValueError('Provide tasks or a targeted clarification, exclusively')
        by_id = {task.id: task for task in self.tasks}
        if len(by_id) != len(self.tasks):
            raise ValueError('Task IDs must be unique')
        pending = set(by_id)
        for task in self.tasks:
            if (len(set(task.depends_on)) != len(task.depends_on)
                    or any(dep not in by_id for dep in task.depends_on)
                    or any(ref.task_id not in task.depends_on for ref in task.inputs)):
                raise ValueError('Invalid task dependency or input reference')
            if task.depends_on and not task.inputs:
                raise ValueError('Dependent tasks require explicit result inputs')
        while pending:
            ready = {key for key in pending if not pending.intersection(by_id[key].depends_on)}
            if not ready:
                raise ValueError('Cyclic task dependencies')
            pending -= ready
        return self
