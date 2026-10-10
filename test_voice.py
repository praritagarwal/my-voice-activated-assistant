"""Run before browser commands: model load, microphone transcription and speaker output."""
import json
from pathlib import Path
from voice_io import VoiceIO
config_path = Path(__file__).with_name('config.json')
if not config_path.exists(): config_path = config_path.with_name('config.example.json')
v = VoiceIO(json.loads(config_path.read_text())['voice'])
v.speak('Speaker test. Hold F8 and say a short sentence.')
text, timing = v.listen()
print('Transcript:', text)
print('Timing:', timing)
if text: v.speak('I heard: ' + text)
