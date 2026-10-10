import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import local_models as models

class LocalModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.config={'model_dir':str(self.root)}
    def tearDown(self):self.tmp.cleanup()
    def prepare(self,kind):
        p=self.root/kind;p.mkdir()
        config={'type':'ONNX2','model_file':'tts.onnx','voices':'voices.npz'} if kind=='kitten' else {}
        (p/'config.json').write_text(json.dumps(config))
        for name in (['tts.onnx','voices.npz'] if kind=='kitten' else ['model.bin','tokenizer.json']):(p/name).write_bytes(b'model')
        (self.root/'ready.json').write_text(json.dumps({'sources':models.voice_sources(self.config)}))
        return p
    def test_ready_local_paths(self):
        for kind in ['whisper','kitten']:
            p=self.prepare(kind);self.assertEqual(models.local_model_path(self.config,kind),p.resolve())
    def test_missing_models_explain_setup(self):
        with self.assertRaisesRegex(RuntimeError,'setup_models.py'):models.local_model_path(self.config,'whisper')
    def test_source_change_rejected(self):
        self.prepare('whisper');self.config['asr_model']='base.en'
        with self.assertRaisesRegex(RuntimeError,'differs'):models.local_model_path(self.config,'whisper')
    def test_empty_file_rejected(self):
        p=self.prepare('whisper');(p/'model.bin').write_bytes(b'')
        with self.assertRaises(RuntimeError):models.local_model_path(self.config,'whisper')
    def test_unsafe_kitten_filename_rejected(self):
        p=self.prepare('kitten');(p/'config.json').write_text(json.dumps({'type':'ONNX2','model_file':'../outside','voices':'voices.npz'}))
        with self.assertRaisesRegex(ValueError,'Unsafe'):models.check_folder('kitten',p)
    def test_offline_flags(self):
        with patch.dict(models.os.environ,{},clear=True):
            models.enable_offline_loading()
            self.assertEqual(models.os.environ['HF_HUB_OFFLINE'],'1')
            self.assertEqual(models.os.environ['TRANSFORMERS_OFFLINE'],'1')

    def test_voice_loaders_receive_local_paths(self):
        import sys
        import types
        from unittest.mock import Mock
        from voice_io import VoiceIO
        whisper=self.prepare('whisper');kitten=self.prepare('kitten')
        whisper_loader=Mock();kitten_loader=Mock()
        modules={'sounddevice':types.SimpleNamespace(),
                 'faster_whisper':types.SimpleNamespace(WhisperModel=whisper_loader),
                 'pynput':types.SimpleNamespace(keyboard=object()),
                 'kittenml':types.SimpleNamespace(KittenTTS=kitten_loader)}
        with patch.dict(sys.modules,modules),patch.dict(models.os.environ,{},clear=True):
            VoiceIO(self.config)
            whisper_loader.assert_called_once_with(str(whisper.resolve()),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
            kitten_loader.assert_called_once_with(str(kitten.resolve()))
            self.assertEqual(models.os.environ['HF_HUB_OFFLINE'],'1')
