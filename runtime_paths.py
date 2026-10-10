"""Read-only application assets and separately writable user data."""
import os
import sys
from pathlib import Path

ASSET_ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))


def data_root():
    override=os.environ.get('TREADMILL_ASSISTANT_HOME')
    if override:return Path(override).expanduser().resolve()
    if getattr(sys,'frozen',False):
        return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'Sitara'
    return Path(__file__).resolve().parent


def config_source():
    local=data_root()/'config.json'
    return local if local.exists() else ASSET_ROOT/'config.example.json'
