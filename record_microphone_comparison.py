"""Record headset microphone samples to diagnose music interference; no browser actions."""
import argparse
import json
import wave
from datetime import datetime, timezone
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent


def metrics(audio,np):
    x=audio.astype('float64')/32768.0
    rms=float(np.sqrt(np.mean(x*x)))
    return {'rms':round(rms,6),'rms_dbfs':round(20*float(np.log10(max(rms,1e-12))),2),
            'peak':round(float(np.max(np.abs(x))),6),
            'clipped_fraction':round(float(np.mean(np.abs(x)>=0.999)),6)}


def record(sd,np,device,seconds):
    chunks=[];frames=int(seconds*16000)
    with sd.InputStream(channels=1,dtype='int16',samplerate=16000,device=device) as mic:
        print('RECORDING NOW',flush=True)
        while frames:
            block,overflow=mic.read(min(1600,frames))
            if overflow: raise RuntimeError('Microphone overflow; sample discarded. Close other listening processes and retry.')
            chunks.append(block.reshape(-1).copy());frames-=len(block)
    return np.concatenate(chunks)


def write_wav(path,audio):
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
        f.writeframes(audio.astype('<i2',copy=False).tobytes())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--condition',required=True,choices=['paused','playing'])
    args=parser.parse_args()
    import numpy as np
    import sounddevice as sd
    path=ROOT/'config.json'
    if not path.exists():path=ROOT/'config.example.json'
    config=json.loads(path.read_text(encoding='utf-8'))['voice'] if path.exists() else {}
    device=config.get('input_device')
    selected=sd.query_devices(device,kind='input')
    print('Microphone:',selected['name'])
    print(f'Condition: {args.condition}. Set music accordingly; this script does not control playback.')
    print('Stop assistant/detector tests. Keep headset, volume, mic position and speaking volume fixed.')
    print('These recordings save your microphone audio, including any background conversation/music.')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    folder=ROOT/'logs'/'microphone_comparison'/f'{stamp}_{args.condition}'
    folder.mkdir(parents=True,exist_ok=True)
    results=[]
    tasks=[('background',5,'Stay silent for five seconds. We want microphone background audio only.'),
           ('wake_phrase',8,'Say "Hey Jarvis" THREE times at your normal volume, with about one second between repetitions.'),
           ('command',8,'Say "Hey Jarvis, play song number six" TWO times at your normal volume, with a pause between repetitions.')]
    try:
        for name,seconds,instruction in tasks:
            print(f'\n{name}: {instruction}')
            input('Press Enter when ready (while stationary)... ')
            for n in (3,2,1):print(n,flush=True);time.sleep(1)
            audio=record(sd,np,device,seconds)
            target=folder/f'{name}.wav';write_wav(target,audio)
            result={'sample':name,'file':target.name,'seconds':seconds,**metrics(audio,np)};results.append(result)
            print('Saved:',target)
            print('Level:',result['rms_dbfs'],'dBFS; peak:',result['peak'])
    except KeyboardInterrupt:print('\nStopped; completed samples retained.')
    report={'condition':args.condition,'microphone':selected['name'],'input_device':device,
            'sample_rate':16000,'samples':results,
            'note':'Whole-clip RMS is not speech SNR. It cannot distinguish music, voice or headset processing.'}
    (folder/'levels.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('\nSamples saved in:',folder)
    print('Listen to background.wav to check for music leakage; compare speech clips across conditions.')
    print('No automatic playback or detector threshold changes were performed.')


if __name__=='__main__':main()
