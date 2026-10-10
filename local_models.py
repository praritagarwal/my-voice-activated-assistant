"""Local model paths and validation shared by setup and runtime."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def voice_sources(config):
    return {'whisper':config.get('asr_model','tiny.en'),
            'kitten':config.get('tts_model','KittenML/kitten-tts-nano-0.8-int8')}


def model_root(config):
    path=Path(config.get('model_dir','models/voice')).expanduser()
    return path if path.is_absolute() else ROOT/path


def required_files(kind, folder):
    if kind=='whisper':return ['model.bin','config.json','tokenizer.json']
    config=json.loads((folder/'config.json').read_text(encoding='utf-8'))
    if config.get('type') not in ('ONNX1','ONNX2'):
        raise ValueError('Only the existing KittenTTS ONNX model family is supported by this setup.')
    names=['config.json',config['model_file'],config['voices']]
    for name in names:
        if not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
            raise ValueError('Unsafe model filename in KittenTTS config')
    return names


def check_folder(kind,folder):
    for name in required_files(kind,folder):
        path=folder/name
        if not path.is_file() or path.stat().st_size==0:raise FileNotFoundError(str(path))


def local_model_path(config,kind):
    root=model_root(config);folder=root/kind
    try:
        manifest=json.loads((root/'ready.json').read_text(encoding='utf-8'))
        if manifest.get('sources',{}).get(kind)!=voice_sources(config)[kind]:
            raise ValueError('Configured model differs from prepared model')
        check_folder(kind,folder)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise RuntimeError(f'Local {kind} model not ready: {exc}. Run python setup_models.py in this environment.') from exc
    return folder.resolve()


def enable_offline_loading():
    # Set before importing Hugging Face clients or the model loaders.
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
