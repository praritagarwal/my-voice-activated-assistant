import runpy
import sys
import types
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

class VadHookTests(unittest.TestCase):
    def run_hook(self,installed):
        calls=[]
        def copy(name):
            calls.append(name)
            if name not in installed:raise PackageNotFoundError(name)
            return [(name+'.dist-info',name+'.dist-info')]
        modules={'PyInstaller':types.ModuleType('PyInstaller'),
                 'PyInstaller.utils':types.ModuleType('PyInstaller.utils'),
                 'PyInstaller.utils.hooks':types.SimpleNamespace(copy_metadata=copy)}
        with patch.dict(sys.modules,modules):
            result=runpy.run_path(str(Path(__file__).resolve().parents[1]/'packaging_hooks'/'hook-webrtcvad.py'))
        return result,calls
    def test_wheel_metadata_and_native_module(self):
        result,calls=self.run_hook({'webrtcvad-wheels'})
        self.assertEqual(calls,['webrtcvad-wheels'])
        self.assertEqual(result['hiddenimports'],['_webrtcvad'])
        self.assertTrue(result['datas'])
    def test_old_distribution_fallback(self):
        result,calls=self.run_hook({'webrtcvad'})
        self.assertEqual(calls,['webrtcvad-wheels','webrtcvad']);self.assertTrue(result['datas'])
    def test_missing_metadata_fails_clearly(self):
        with self.assertRaisesRegex(RuntimeError,'metadata missing'):self.run_hook(set())
