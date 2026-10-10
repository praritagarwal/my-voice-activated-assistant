import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import launch_assistant as launcher
import runtime_paths

class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_data_override(self):
        with patch.dict(os.environ,{'TREADMILL_ASSISTANT_HOME':str(self.root)}):self.assertEqual(runtime_paths.data_root(),self.root.resolve())
    def test_frozen_user_directory(self):
        with patch.object(runtime_paths.sys,'frozen',True,create=True),patch.dict(os.environ,{'LOCALAPPDATA':str(self.root)}):self.assertEqual(runtime_paths.data_root(),self.root/'Sitara')
    def test_create_default_debug_off(self):
        with patch.object(launcher,'data_root',return_value=self.root):
            path=launcher.ensure_config();self.assertFalse(json.loads(path.read_text())['debug_mode'])
    def test_preserve_personal_config(self):
        path=self.root/'config.json';path.write_text('{"personal":true}')
        with patch.object(launcher,'data_root',return_value=self.root):launcher.ensure_config()
        self.assertEqual(path.read_text(),'{"personal":true}')
    def test_import_refuses_existing_config(self):
        (self.root/'config.json').write_text('{}')
        with patch.object(launcher,'data_root',return_value=self.root):
            with self.assertRaisesRegex(ValueError,'already'):launcher.import_data(self.root/'other')
    def test_existing_ollama_does_not_spawn(self):
        with patch.object(launcher,'http_json',return_value={'models':[{'name':'qwen3:1.7b'}]}),patch.object(launcher.subprocess,'Popen') as spawn:
            launcher.ensure_ollama({'ollama_url':'http://127.0.0.1:11434/api/chat','model':'qwen3:1.7b'});spawn.assert_not_called()
    def test_missing_llm_is_clear(self):
        with patch.object(launcher,'http_json',return_value={'models':[]}):
            with self.assertRaisesRegex(RuntimeError,'ollama pull'):launcher.ensure_ollama({'ollama_url':'http://127.0.0.1:11434/api/chat','model':'qwen3:1.7b'})
    def test_import_copies_models_and_preserves_settings(self):
        source=self.root/'source';source.mkdir();target=self.root/'target';voice=source/'models'/'voice'
        if getattr(self,'default_destination',False):
            with patch.object(launcher,'data_root',return_value=target):launcher.ensure_config()
        for kind in ['whisper','kitten']:(voice/kind).mkdir(parents=True)
        (voice/'whisper'/'config.json').write_text('{}')
        for name in ['model.bin','tokenizer.json']:(voice/'whisper'/name).write_bytes(b'test')
        (voice/'kitten'/'config.json').write_text(json.dumps({'type':'ONNX2','model_file':'tts.onnx','voices':'voices.npz'}))
        for name in ['tts.onnx','voices.npz']:(voice/'kitten'/name).write_bytes(b'test')
        (voice/'ready.json').write_text('{}');wake=source/'models'/'openwakeword';wake.mkdir()
        from openwakeword_trials import MODEL_FILES
        for name in MODEL_FILES:(wake/name).write_bytes(b'test')
        (source/'config.json').write_text(json.dumps({'voice':{'input_device':1},'debug_mode':True}))
        with patch.object(launcher,'data_root',return_value=target):launcher.import_data(source)
        config=json.loads((target/'config.json').read_text());self.assertEqual(config['voice']['input_device'],1)
        self.assertFalse(config['debug_mode']);self.assertTrue((target/'models'/'voice'/'ready.json').is_file())

    def test_existing_chrome_detected(self):
        from types import SimpleNamespace
        with patch.object(launcher.os,'name','nt'),patch.object(launcher.subprocess,'run',return_value=SimpleNamespace(stdout='"chrome.exe","123"\n')):
            self.assertTrue(launcher.chrome_running())

    def test_default_config_from_failed_first_launch_allows_import(self):
        self.default_destination=True
        self.test_import_copies_models_and_preserves_settings()
