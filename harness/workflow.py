"""Actual openJiuwen execution; never a marker-only dependency."""
from openjiuwen.core.workflow import Workflow, WorkflowComponent, Start, End, create_workflow_session
from openjiuwen.core.runner import Runner
from openjiuwen.core.session import WORKFLOW_EXECUTE_TIMEOUT
from harness.execution import execute
from harness.tasks import Task
from pathlib import Path
import time


class SolveComponent(WorkflowComponent):
    def __init__(self, agent=None):
        super().__init__()
        self.agent = agent

    async def invoke(self, inputs, session, context):
        return {"record": execute(Task.load(Path(inputs["directory"])), agent=self.agent)}


def build_workflow(agent=None):
    flow = Workflow()
    flow.set_start_comp("start", Start(), inputs_schema={"directory": "${directory}"})
    flow.add_workflow_comp("solve", SolveComponent(agent), inputs_schema={"directory": "${start.directory}"})
    flow.set_end_comp("end", End(), inputs_schema={"record": "${solve.record}"})
    flow.add_connection("start", "solve")
    flow.add_connection("solve", "end")
    return flow


async def run_task(flow, task, *, deadline=None):
    # SDK0.1.19 defaults to 60s per workflow. Its Runner envs argument is not
    # applied by this version, so pass a configured public Session explicitly.
    # The agent/HTTP/tools retain their own limits and the global run deadline;
    # this small grace lets an already-finishing component publish/clean up.
    remaining = max(0.0, deadline-time.monotonic()) if deadline is not None else 3300.0
    session = create_workflow_session(session_id=task.task_id,
        envs={WORKFLOW_EXECUTE_TIMEOUT: remaining+30.0})
    return await Runner.run_workflow(flow, {"directory": str(task.directory)}, session=session)
