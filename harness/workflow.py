"""Actual openJiuwen execution; never a marker-only dependency."""
from openjiuwen.core.workflow import Workflow, WorkflowComponent, Start, End
from openjiuwen.core.runner import Runner
from harness.execution import execute
from harness.tasks import Task
from pathlib import Path


class SolveComponent(WorkflowComponent):
    async def invoke(self, inputs, session, context):
        return {"record": execute(Task.load(Path(inputs["directory"])))}


def build_workflow():
    flow = Workflow()
    flow.set_start_comp("start", Start(), inputs_schema={"directory": "${directory}"})
    flow.add_workflow_comp("solve", SolveComponent(), inputs_schema={"directory": "${start.directory}"})
    flow.set_end_comp("end", End(), inputs_schema={"record": "${solve.record}"})
    flow.add_connection("start", "solve")
    flow.add_connection("solve", "end")
    return flow


async def run_task(flow, task):
    await Runner.run_workflow(flow, {"directory": str(task.directory)}, session=task.task_id)
