"""Real SDK timeout regression without a minute-long test or any model request."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('openjiuwen'),'openJiuwen not installed')
class WorkflowTimeoutTests(unittest.TestCase):
    def test_explicit_session_overrides_sdk_timeout_and_later_task_runs(self):
        from openjiuwen.core.workflow import Workflow,WorkflowComponent,Start,End
        from openjiuwen.core.runner import Runner
        from openjiuwen.core.session import WORKFLOW_EXECUTE_TIMEOUT
        from harness.workflow import run_task
        observed=[]
        class Delay(WorkflowComponent):
            async def invoke(self,inputs,session,context):
                observed.append(session.get_env(WORKFLOW_EXECUTE_TIMEOUT))
                await asyncio.sleep(.06)
                return {'record':{'done':True}}
        def flow():
            f=Workflow();f.set_start_comp('start',Start(),inputs_schema={'directory':'${directory}'})
            f.add_workflow_comp('delay',Delay(),inputs_schema={'directory':'${start.directory}'})
            f.set_end_comp('end',End(),inputs_schema={'record':'${delay.record}'})
            f.add_connection('start','delay');f.add_connection('delay','end');return f
        async def scenario():
            with patch.dict(os.environ,{'WORKFLOW_EXECUTE_TIMEOUT':'0.02'}):
                with self.assertRaises(Exception) as error:
                    await Runner.run_workflow(flow(),{'directory':'unused'},session='old-default-timeout')
                self.assertIn('time limit',str(error.exception))
                task=SimpleNamespace(directory=Path('/unused'),task_id='configured-slow')
                configured=flow()
                await run_task(configured,task,deadline=time.monotonic()+2)
                await run_task(configured,SimpleNamespace(directory=Path('/next'),task_id='next-task'),deadline=time.monotonic()+2)
        asyncio.run(scenario())
        self.assertAlmostEqual(observed[0],.02)
        self.assertTrue(all(30 < x <= 32 for x in observed[1:]))
        self.assertEqual(len(observed),3)


if __name__=='__main__':unittest.main()
