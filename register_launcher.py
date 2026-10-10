"""Run once in the working Conda environment to enable double-click source startup."""
import sys
from pathlib import Path
root=Path(__file__).resolve().parent
(root/'launcher_python.txt').write_text(sys.executable+'\n',encoding='utf-8')
print('Launcher registered. Double-click Start_Sitara.bat to start with this Python environment.')
