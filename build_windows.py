"""Build on Windows using the verified Python 3.11 environment; not a cross-compiler."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def main():
    if os.name!='nt':raise RuntimeError('Build Sitara on Windows. PyInstaller cannot cross-compile this Windows app from Linux.')
    if sys.version_info[:2]!=(3,11):raise RuntimeError('Use the verified Python 3.11 Conda environment.')
    required=['flask','requests','numpy','sounddevice','faster_whisper','pynput','kittenml','openwakeword','onnxruntime','webrtcvad','espeakng_loader']
    for name in required:
        if importlib.util.find_spec(name) is None:raise RuntimeError(f'Missing {name}; build inside your working voice environment.')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--console','--name','Sitara',
             '--icon',str(ROOT/'assets'/'sitara.ico'),
             '--additional-hooks-dir',str(ROOT/'packaging_hooks'),
             '--add-data',str(ROOT/'config.example.json')+os.pathsep+'.',
             '--add-data',str(ROOT/'assets')+os.pathsep+'assets']
    for name in ['faster_whisper','openwakeword','ctranslate2','sounddevice','soundfile','espeakng_loader','phonemizer']:
        command+=['--collect-all',name]
    command+=['--collect-binaries','onnxruntime','--collect-data','onnxruntime',
              '--exclude-module','onnxruntime.quantization',
              '--collect-data','kittenml','--copy-metadata','kittenml','--copy-metadata','huggingface_hub',
              '--hidden-import','kittenml.kittentts_legacy.onnx_model','--hidden-import','pynput.keyboard._win32',
              '--exclude-module','kittenml.kittentts2','--exclude-module','torch','--exclude-module','tensorflow',
              '--exclude-module','sherpa_onnx','--exclude-module','sentencepiece',str(ROOT/'launch_assistant.py')]
    subprocess.run(command,cwd=ROOT,check=True)
    folder=ROOT/'dist'/'Sitara'
    shutil.copytree(ROOT/'extension',folder/'extension',dirs_exist_ok=True)
    for name in ['README.md','Start_Sitara.bat','config.example.json']:
        shutil.copy2(ROOT/name,folder/name)
    if (ROOT/'LICENSE').is_file():shutil.copy2(ROOT/'LICENSE',folder/'LICENSE')
    shutil.make_archive(str(ROOT/'dist'/'Sitara-Windows'),'zip',ROOT/'dist','Sitara')
    (ROOT/'build'/'build_environment.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True),encoding='utf-8')
    print('Built:',folder)
    print('Import existing data once: Sitara.exe --import-data "PATH_TO_YOUR_SOURCE_PROJECT"')
    print('Then install extension/ in Chrome once and double-click Start_Sitara.bat.')


if __name__=='__main__':main()
