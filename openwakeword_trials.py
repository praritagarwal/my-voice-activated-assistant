"""Standalone Hey Jarvis comparison. Copy beside your assistant's config.json."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import urllib.request
import shutil

from runtime_paths import data_root, config_source
ROOT = data_root()
MODEL_DIR = ROOT/'models'/'openwakeword'
URL_ROOT = 'https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/'
MODEL_FILES = ['hey_jarvis_v0.1.onnx','melspectrogram.onnx','embedding_model.onnx']


def setup():
    MODEL_DIR.mkdir(parents=True,exist_ok=True)
    for name in MODEL_FILES:
        path=MODEL_DIR/name
        if path.is_file() and path.stat().st_size > 0: continue
        print('Downloading',name,flush=True)
        temporary=path.with_suffix('.download')
        try:
            with urllib.request.urlopen(URL_ROOT+name,timeout=60) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response,output)
            if not temporary.stat().st_size: raise RuntimeError('Empty model download')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    print('Models downloaded. Setup requires internet; detection runs locally.')


def detect_once(model, sd, device, threshold, seconds=5, clock=time.monotonic, prompt=print, gain=None):
    model.reset()
    peak=0.0
    with sd.InputStream(channels=1,dtype='int16',samplerate=16000,device=device) as mic:
        prompt(f'Say "Hey Jarvis" now — {seconds:g} seconds.',flush=True)
        started=clock(); deadline=started+seconds
        while clock()<deadline:
            samples,overflow=mic.read(1280)  # native 80 ms frames
            if overflow: raise RuntimeError('Microphone overflow; this trial is invalid, not a miss')
            if clock()>=deadline: break
            audio=samples.reshape(-1)
            if gain is not None: audio=gain.process_pcm(audio)
            scores=model.predict(audio)
            score=max((float(v) for v in scores.values()),default=0.0)
            peak=max(peak,score)
            now=clock()
            if score>=threshold and now<=deadline:
                return {'detected':True,'latency_seconds':round(now-started,3),'peak_score':round(peak,4), 'audio_gain':gain.diagnostics() if gain is not None else None}
        return {'detected':False,'latency_seconds':None,'peak_score':round(peak,4), 'audio_gain':gain.diagnostics() if gain is not None else None}


def cue(sd,np,device):
    rate=24000;t=np.arange(6000)/rate
    fade=np.minimum(1,np.minimum(t/0.01,(0.25-t)/0.01))
    sd.play((0.35*fade*np.sin(2*np.pi*880*t)).astype('float32'),rate,device=device)
    sd.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup',action='store_true',help='Download official ONNX models and exit')
    parser.add_argument('--condition',choices=['paused','playing','unspecified'],default='unspecified')
    parser.add_argument('--no-agc',action='store_true',help='Disable gain for comparison')
    parser.add_argument('--threshold',type=float,default=0.5)
    args=parser.parse_args()
    if args.setup: setup();return
    if not 0<args.threshold<=1: parser.error('Threshold must be greater than 0 and at most 1')
    for name in MODEL_FILES:
        if not (MODEL_DIR/name).is_file(): parser.error('Models missing; run python openwakeword_trials.py --setup')
    import numpy as np
    import sounddevice as sd
    from openwakeword.model import Model
    path=config_source()
    config=json.loads(path.read_text(encoding='utf-8'))['voice'] if path.exists() else {}
    model=Model(wakeword_models=[str(MODEL_DIR/MODEL_FILES[0])],inference_framework='onnx',
                melspec_model_path=str(MODEL_DIR/MODEL_FILES[1]),embedding_model_path=str(MODEL_DIR/MODEL_FILES[2]),ncpu=1)
    from audio_gain import SpeechGain
    gain_settings=dict(config.get('gain', {}))
    if args.no_agc: gain_settings['enabled']=False
    print('Automatic gain:', gain_settings.get('enabled',True))
    print(f'openWakeWord: Hey Jarvis. Condition: {args.condition}; threshold: {args.threshold}.')
    print('10 attempts, 5 seconds each. Speak once at normal pace after each beep/prompt.')
    print('No browser actions. Keep headset, volume and microphone position fixed across runs.')
    input('Set the music condition, then press Enter to start while stationary... ')
    results=[];interrupted=False
    try:
        for i in range(1,11):
            print(f'\nAttempt {i}/10',flush=True)
            cue(sd,np,config.get('output_device'))
            r=detect_once(model,sd,config.get('input_device'),args.threshold,gain=SpeechGain(gain_settings));r['trial']=i;results.append(r)
            print((f"DETECTED ({r['latency_seconds']:.2f}s)" if r['detected'] else 'MISS — no detection within 5 seconds.')+f" Peak score: {r['peak_score']:.3f}",flush=True)
            print('Audio gain:', json.dumps(r['audio_gain']), flush=True)
            if i<10: time.sleep(1)
    except KeyboardInterrupt:
        interrupted=True;print('\nInterrupted; retaining completed trials only.')
    except Exception as exc:
        interrupted=True;print(f'\nStopped: {exc}. Current trial not counted.')
    hits=sum(r['detected'] for r in results);total=len(results)
    print(f'\nSummary [{args.condition}]: {hits}/{total} detected; {total-hits} missed.')
    if total: print(f'Detection rate: {100*hits/total:.0f}%')
    print('Latency includes your response time. Prompted trials do not measure false-trigger rate.')
    folder=ROOT/'logs'/'wake_tests';folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    output=folder/f'{stamp}_openwakeword_{args.condition}.json'
    output.write_text(json.dumps({'detector':'openWakeWord','phrase':'Hey Jarvis','condition':args.condition,
        'threshold':args.threshold,'gain_settings':gain_settings,'input_device':config.get('input_device'),'window_seconds':5,
        'requested_trials':10,'completed_trials':total,'interrupted':interrupted,
        'detections':hits,'misses':total-hits,'trials':results},indent=2)+'\n',encoding='utf-8')
    print('Results saved:',output)


if __name__=='__main__':main()
