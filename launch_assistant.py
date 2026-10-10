"""Windows/source launcher. Built executable uses per-user data; source keeps existing data."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
from runtime_paths import data_root, ASSET_ROOT, config_source


def ensure_config():
    root=data_root();root.mkdir(parents=True,exist_ok=True)
    path=root/'config.json'
    if not path.exists():
        config=json.loads((ASSET_ROOT/'config.example.json').read_text(encoding='utf-8'))
        config['debug_mode']=False
        path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    return path


def import_data(source):
    source=Path(source).expanduser().resolve();destination=data_root().resolve()
    if source==destination:raise ValueError('Source and destination must differ')
    if (destination/'models').exists():
        raise ValueError('Destination already has models. Import is only for a fresh installation.')
    existing=destination/'config.json'
    if existing.exists():
        defaults=json.loads((ASSET_ROOT/'config.example.json').read_text(encoding='utf-8'))
        defaults['debug_mode']=False
        if json.loads(existing.read_text(encoding='utf-8'))!=defaults:
            raise ValueError('Destination already has personal settings; import will not overwrite them.')
    config=json.loads((source/'config.json' if (source/'config.json').exists() else source/'config.example.json').read_text(encoding='utf-8'))
    voice=config.get('voice',{})
    model_dir=Path(voice.get('model_dir','models/voice'))
    if not model_dir.is_absolute():model_dir=source/model_dir
    from local_models import check_folder
    check_folder('whisper',model_dir/'whisper')
    if voice.get('tts_enabled',True):check_folder('kitten',model_dir/'kitten')
    if not (model_dir/'ready.json').is_file():raise ValueError('Prepared voice-model manifest missing')
    from openwakeword_trials import MODEL_FILES
    for name in MODEL_FILES:
        if not (source/'models'/'openwakeword'/name).is_file():raise ValueError('Wake model missing: '+name)
    destination.mkdir(parents=True,exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix='sitara-import-',dir=destination.parent) as temp:
        staged=Path(temp)
        shutil.copytree(model_dir,staged/'models'/'voice')
        shutil.copytree(source/'models'/'openwakeword',staged/'models'/'openwakeword')
        voice['model_dir']='models/voice';config['voice']=voice;config['debug_mode']=False
        (staged/'config.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
        (staged/'models').replace(destination/'models')
        (staged/'config.json').replace(destination/'config.json')
    print('Imported existing settings and model files to',destination)


def first_run_setup():
    """Choose existing prepared data or an explicit first-time download."""
    import tkinter as tk
    from tkinter import filedialog
    root=tk.Tk();root.title('Set up Sitara');root.resizable(False,False)
    choice={'action':None,'folder':None}
    try:
        icon=ASSET_ROOT/'assets'/'sitara.ico'
        if icon.is_file():root.iconbitmap(str(icon))
    except tk.TclError:pass
    tk.Label(root,text='Welcome to Sitara',font=('Segoe UI',16,'bold')).pack(padx=28,pady=(24,10))
    tk.Label(root,text='Choose how to prepare your local voice models.\nIf you used the Python version, import that project folder.',
             font=('Segoe UI',10),justify='left').pack(padx=28,pady=(0,18))
    def select_import():
        folder=filedialog.askdirectory(parent=root,title='Select your treadmill_assistant project folder')
        if folder:choice.update(action='import',folder=folder);root.destroy()
    def select_download():choice.update(action='download');root.destroy()
    tk.Button(root,text='Import existing setup…',width=32,command=select_import).pack(padx=28,pady=5)
    tk.Button(root,text='Download models (internet required)',width=32,command=select_download).pack(padx=28,pady=5)
    tk.Button(root,text='Cancel',width=32,command=root.destroy).pack(padx=28,pady=(5,24))
    root.mainloop()
    if choice['action']=='import':import_data(choice['folder'])
    elif choice['action']=='download':
        import setup_models
        setup_models.prepare(json.loads(config_source().read_text(encoding='utf-8')).get('voice',{}))
        from openwakeword_trials import setup
        setup()
    else:return False
    return True


def chrome_path():
    if os.name=='nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') as key:
                    path=Path(winreg.QueryValue(key,None))
                    if path.is_file():return str(path)
            except OSError:pass
    for base in ('LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)'):
        if os.environ.get(base):
            path=Path(os.environ[base])/'Google'/'Chrome'/'Application'/'chrome.exe'
            if path.is_file():return str(path)
    return shutil.which('chrome') or shutil.which('google-chrome')


def chrome_running():
    if os.name!='nt':return False
    try:
        result=subprocess.run(['tasklist','/FI','IMAGENAME eq chrome.exe','/FO','CSV','/NH'],
                              capture_output=True,text=True,timeout=3)
        return any(line.lower().startswith('"chrome.exe",') for line in result.stdout.splitlines())
    except (OSError,subprocess.TimeoutExpired):return False


def http_json(url):
    with urllib.request.urlopen(url,timeout=2) as response:return json.load(response)


def ensure_ollama(config):
    from urllib.parse import urlsplit
    url=urlsplit(config['ollama_url'])
    tags=f'{url.scheme}://{url.netloc}/api/tags'
    try:models=http_json(tags)
    except Exception:
        if url.hostname not in ('localhost','127.0.0.1'):raise RuntimeError('Configured Ollama server is unavailable')
        executable=shutil.which('ollama')
        candidate=Path(os.environ.get('LOCALAPPDATA',''))/'Programs'/'Ollama'/'ollama.exe'
        if not executable and candidate.is_file():executable=str(candidate)
        if not executable:raise RuntimeError('Start or install Ollama, then retry.')
        subprocess.Popen([executable,'serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+15
        while True:
            try:models=http_json(tags);break
            except Exception:
                if time.monotonic()>=deadline:raise RuntimeError('Ollama did not start; open Ollama and retry.')
                time.sleep(0.3)
    names={m.get('name') for m in models.get('models',[])}
    wanted=config['model']
    if wanted not in names and wanted+':latest' not in names:
        raise RuntimeError(f'Ollama model missing. Run: ollama pull {wanted}')


def main():
    parser=argparse.ArgumentParser(description=__doc__,epilog="Default: wake input. Pass --voice for stationary F8 input.")
    parser.add_argument('--setup-models',action='store_true')
    parser.add_argument('--check-models',action='store_true')
    parser.add_argument('--import-data')
    parser.add_argument('--debug',action='store_true')
    parser.add_argument('--no-chrome',action='store_true')
    options,remaining=parser.parse_known_args()
    if options.import_data:import_data(options.import_data);return
    ensure_config()
    if options.setup_models or options.check_models:
        import setup_models
        sys.argv=[sys.argv[0]]+(['--check'] if options.check_models else [])
        setup_models.main();return
    config=json.loads(config_source().read_text(encoding='utf-8'))
    from local_models import local_model_path
    def check_voice():
        local_model_path(config.get('voice',{}),'whisper')
        if config.get('voice',{}).get('tts_enabled',True):local_model_path(config.get('voice',{}),'kitten')
    try:check_voice()
    except RuntimeError:
        if not getattr(sys,'frozen',False):raise
        if not first_run_setup():return
        config=json.loads(config_source().read_text(encoding='utf-8'))
        check_voice()
    if getattr(sys,'frozen',False) and config.get('voice',{}).get('wake',{}).get('backend','openwakeword')!='openwakeword':
        raise RuntimeError('This Windows beta packages the verified Hey Jarvis backend only.')
    port=int(config.get('port',8765))
    try:health=http_json(f'http://127.0.0.1:{port}/health')
    except Exception:health=None
    if health and health.get('service')=='treadmill-assistant':
        print('Assistant is already running. Use its existing window.');return
    ensure_ollama(config)
    if not options.no_chrome and not chrome_running():
        chrome=chrome_path()
        if not chrome:raise RuntimeError('Chrome was not found. Open Chrome and use --no-chrome, or install Chrome.')
        subprocess.Popen([chrome,'https://www.youtube.com/'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    args=remaining or ['--wake']
    if not options.debug and '--no-debug' not in args:args.append('--no-debug')
    if options.debug:config['debug_mode']=True
    sys.argv=[sys.argv[0]]+args
    import assistant
    assistant.DEBUG_MODE=options.debug
    if options.debug:
        assistant.LOG_DIR.mkdir(exist_ok=True);assistant.SCREEN_DIR.mkdir(exist_ok=True)
    assistant.main()


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except Exception as exc:
        print('Startup failed:',exc)
        print('Settings/models folder:',data_root())
        print('Use --setup-models to download models, or --check-models to validate them.')
        if getattr(sys,'frozen',False):input('Press Enter to close...')
        sys.exit(1)
