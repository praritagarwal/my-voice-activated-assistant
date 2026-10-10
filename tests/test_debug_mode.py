import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from typing import Any


class DebugModeTests(unittest.TestCase):
    def test_disabled_diagnostics_never_queue_or_log(self):
        source=Path(__file__).resolve().parents[1]/'assistant.py'
        tree=ast.parse(source.read_text())
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('browser_snapshot','log_event')]
        queue=Mock();lock=Mock();save=Mock()
        namespace={'DEBUG_MODE':False,'COMMANDS':queue,'LOG_LOCK':lock,'save_browser_state':save,'Any':Any}
        exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),namespace)
        self.assertEqual(namespace['browser_snapshot']('test','before'),{'ok':True,'skipped':True})
        namespace['log_event']('test','event')
        queue.put.assert_not_called()
        save.assert_not_called()


if __name__=='__main__':unittest.main()
