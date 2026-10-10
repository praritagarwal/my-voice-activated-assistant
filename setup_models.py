"""Prepare voice models once; runtime never downloads them. Setup requires internet."""
import argparse
import json
import os
from local_models import ROOT, voice_sources, model_root, local_model_path, check_folder, required_files


def load_config():
    from runtime_paths import config_source
    path=config_source()
    return json.loads(path.read_text(encoding='utf-8')).get('voice',{})


def prepare(config):
    # This command is the explicit online download boundary.
    os.environ.pop('HF_HUB_OFFLINE',None)
    os.environ.pop('TRANSFORMERS_OFFLINE',None)
    from faster_whisper.utils import download_model
    from huggingface_hub import hf_hub_download, snapshot_download
    root=model_root(config);root.mkdir(parents=True,exist_ok=True)
    sources=voice_sources(config)
    print('Preparing Whisper:',sources['whisper'],flush=True)
    download_model(sources['whisper'],output_dir=str(root/'whisper'))
    check_folder('whisper',root/'whisper')
    prepared={'whisper':sources['whisper']}
    if config.get('tts_enabled',True):
        print('Preparing KittenTTS:',sources['kitten'],flush=True)
        folder=root/'kitten'
        hf_hub_download(repo_id=sources['kitten'],filename='config.json',local_dir=str(folder))
        names=required_files('kitten',folder)
        snapshot_download(repo_id=sources['kitten'],local_dir=str(folder),allow_patterns=names)
        check_folder('kitten',folder)
        prepared['kitten']=sources['kitten']
    temporary=root/'ready.json.tmp'
    temporary.write_text(json.dumps({'sources':prepared},indent=2)+'\n',encoding='utf-8')
    temporary.replace(root/'ready.json')


def verify(config,include_wake=True):
    for kind in ['whisper']+(['kitten'] if config.get('tts_enabled',True) else []):
        print('Ready:',kind,local_model_path(config,kind))
    if include_wake:
        backend=config.get('wake',{}).get('backend','openwakeword')
        if backend=='openwakeword':
            from openwakeword_trials import MODEL_DIR,MODEL_FILES
            for name in MODEL_FILES:
                path=MODEL_DIR/name
                if not path.is_file() or path.stat().st_size==0:raise RuntimeError(f'Missing wake model: {path}')
            print('Ready: Hey Jarvis wake models')
        else:print('Sherpa wake models remain managed by setup_wake.py.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Validate prepared files without downloads')
    parser.add_argument('--voice-only',action='store_true',help='Skip wake model setup/check')
    args=parser.parse_args();config=load_config()
    try:
        if not args.check:
            prepare(config)
            if not args.voice_only and config.get('wake',{}).get('backend','openwakeword')=='openwakeword':
                from openwakeword_trials import setup
                setup()
        verify(config,include_wake=not args.voice_only)
        print('Local model files ready. Normal assistant startup now loads offline.')
    except Exception as exc:
        parser.exit(1,f'Model setup failed: {exc}\n')


if __name__=='__main__':main()
