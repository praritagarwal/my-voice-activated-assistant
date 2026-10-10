"""Download the official English KWS model once; no custom training required."""
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request
from wake_word import MODEL_NAME, MODEL_DIR, SUFFIX

URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/' + MODEL_NAME + '.tar.bz2'


def install():
    required = ['tokens.txt','bpe.model'] + [p + '-' + SUFFIX for p in ('encoder','decoder','joiner')]
    if all((MODEL_DIR/p).is_file() for p in required):
        print('Wake model already installed.'); return
    MODEL_DIR.parent.mkdir(parents=True,exist_ok=True)
    print('Downloading official English sherpa-onnx model...')
    with tempfile.TemporaryDirectory(dir=MODEL_DIR.parent) as folder:
        archive = Path(folder)/'model.tar.bz2'
        with urllib.request.urlopen(URL,timeout=60) as response, archive.open('wb') as dest:
            shutil.copyfileobj(response,dest)
        # Extract only expected regular files, never archive paths or links.
        staged = Path(folder)/'staged'; staged.mkdir()
        with tarfile.open(archive,'r:bz2') as tar:
            for name in required:
                member = tar.getmember(MODEL_NAME+'/'+name)
                if not member.isfile(): raise ValueError('Expected a regular model file: '+name)
                with tar.extractfile(member) as source, (staged/name).open('wb') as dest:
                    shutil.copyfileobj(source,dest)
        MODEL_DIR.mkdir(exist_ok=True)
        for name in required: os.replace(staged/name,MODEL_DIR/name)
    print('Installed wake model. Run python test_wake.py next.')


if __name__ == '__main__': install()
