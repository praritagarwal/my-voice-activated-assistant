"""Ten prompted five-second wake trials. Place beside assistant.py and wake_word.py."""
import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import time

from wake_word import WakeInput


def detect_once(wake, seconds=5.0, clock=time.monotonic, prompt=print):
    """New detector state per trial; timeout is measured after microphone opens."""
    stream = wake.spotter.create_stream()
    with wake.sd.InputStream(channels=1, dtype='float32', samplerate=16000,
                             device=wake.config.get('input_device')) as mic:
        prompt(f'Say "{wake.phrase}" now — {seconds:g} seconds.', flush=True)
        started = clock()
        deadline = started + seconds
        while clock() < deadline:
            samples, overflow = mic.read(800)  # 50 ms blocks, short timeout granularity
            if overflow:
                raise RuntimeError('Microphone overflow: trial invalid; not counted as a miss.')
            if clock() >= deadline: break
            stream.accept_waveform(16000, samples.reshape(-1))
            while wake.spotter.is_ready(stream):
                wake.spotter.decode_stream(stream)
                result = wake.spotter.get_result(stream)
                now = clock()
                if result and now <= deadline:
                    wake.spotter.reset_stream(stream)
                    return {'detected': True, 'latency_seconds': round(now-started,3), 'keyword': str(result)}
                if now >= deadline: break
        return {'detected': False, 'latency_seconds': None, 'keyword': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--condition', choices=['paused','playing','unspecified'], default='unspecified',
                        help='Label only; this script does not control YouTube.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    path = root/'config.json'
    if not path.exists(): path = root/'config.example.json'
    config = copy.deepcopy(json.loads(path.read_text(encoding='utf-8'))['voice'])
    config.setdefault('wake', {})['phrase'] = 'Hey Assistant'
    wake = WakeInput(config)
    print(f'Condition: {args.condition}. This test performs no browser actions.')
    print('Ten trials. Speak once at your normal pace after each prompt/beep.')
    print('Leave microphone, volume and detector settings unchanged between runs.')
    input('Set music to the desired condition, then press Enter to begin while stationary... ')
    results = []
    interrupted = False
    try:
        for trial in range(1,11):
            print(f'\nAttempt {trial}/10', flush=True)
            wake.cue()  # microphone closed during cue
            result = detect_once(wake)
            result['trial'] = trial
            results.append(result)
            print(f"DETECTED ({result['latency_seconds']:.2f}s)" if result['detected'] else 'MISS — no detection within 5 seconds.', flush=True)
            if trial < 10: time.sleep(1)
    except KeyboardInterrupt:
        interrupted = True
        print('\nTest interrupted; retaining completed trials only.')
    except Exception as exc:
        interrupted = True
        print(f'\nTest stopped: {exc}. Current trial is invalid, not a negative.')
    hits = sum(r['detected'] for r in results)
    total = len(results)
    print(f'\nSummary [{args.condition}]: {hits}/{total} detected; {total-hits} missed.')
    if total: print(f'Detection rate: {100*hits/total:.0f}%')
    print('Times include your response time after the prompt; they are not pure detector latency.')
    print('This measures prompted detection, not background false-trigger rate.')
    folder = root/'logs'/'wake_tests'; folder.mkdir(parents=True,exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    output = folder/f'{stamp}_{args.condition}.json'
    output.write_text(json.dumps({'condition':args.condition,'config_source':path.name,
        'phrase':wake.phrase,'wake_settings':config['wake'],'input_device':config.get('input_device'),
        'window_seconds':5,'requested_trials':10,'completed_trials':total,'interrupted':interrupted,
        'detections':hits,'misses':total-hits,'trials':results},indent=2)+'\n',encoding='utf-8')
    print('Results saved:', output)


if __name__ == '__main__': main()
