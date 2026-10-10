"""Detection only: does not load Whisper/TTS or execute browser commands."""
import json
from pathlib import Path
from wake_word import WakeInput
p = Path(__file__).with_name('config.json')
if not p.exists(): p = p.with_name('config.example.json')
wake = WakeInput(json.loads(p.read_text(encoding='utf-8'))['voice'])
print('Say the wake phrase, pause for the beep. Also test ordinary speech/YouTube for false activations.')
try:
    count=0
    while True:
        result=wake.wait(); count+=1
        print(f'Detection {count}: {result}')
        wake.cue()
except KeyboardInterrupt:
    print('\nStopped.')
