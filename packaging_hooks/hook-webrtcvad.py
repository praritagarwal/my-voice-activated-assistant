"""Support the wheel distribution, which imports as webrtcvad."""
from importlib.metadata import PackageNotFoundError
from PyInstaller.utils.hooks import copy_metadata

hiddenimports=['_webrtcvad']
datas=[]
for distribution in ('webrtcvad-wheels','webrtcvad'):
    try:
        datas=copy_metadata(distribution)
        break
    except PackageNotFoundError:
        continue
else:
    raise RuntimeError('WebRTC VAD package metadata missing; install requirements-openwakeword.txt in the build environment.')
