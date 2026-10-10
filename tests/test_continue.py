import ast
import re
import unittest
from pathlib import Path
from typing import Any

class ContinueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/'assistant.py'
        nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ('direct_playback_command','guard_command_intent','validate_tool_call')]
        cls.ns={'re':re,'Any':Any}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),cls.ns)
    def test_continue_direct(self):
        for text in ['Continue.','Resume','Please continue the current video','carry on','keep playing','resume playback please']:
            self.assertEqual(self.ns['direct_playback_command'](text),{'tool':'media_control','action':'play'})
    def test_other_play_requests_not_overridden(self):
        for text in ['play video 6','play playlist 2','scroll down','pause']:
            self.assertIsNone(self.ns['direct_playback_command'](text))
    def test_unrequested_scroll_rejected(self):
        command={'tool':'scroll_page','direction':'down','fraction':0.5}
        self.assertEqual(self.ns['guard_command_intent']('Continue.',command),{'tool':'resume_current'})
        self.assertEqual(self.ns['guard_command_intent']('scroll down',command),command)
    def test_fallback_allowed(self):
        self.assertEqual(self.ns['validate_tool_call']({'tool':'resume_current'}),{'tool':'resume_current'})
