"""Optional local sherpa-onnx keyword spotting and VAD command capture."""
from pathlib import Path
import time

from runtime_paths import data_root, config_source
ROOT = data_root()
MODEL_NAME = 'sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01'
MODEL_DIR = ROOT / 'models' / MODEL_NAME
SUFFIX = 'epoch-12-avg-2-chunk-16-left-64.int8.onnx'


class CommandBoundary:
    """Track speech/silence independently of audio hardware."""
    def __init__(self, frame_seconds=0.03, start_timeout=5, silence_seconds=0.9, maximum=15):
        self.dt = frame_seconds
        self.start_timeout, self.silence_limit, self.maximum = start_timeout, silence_seconds, maximum
        self.elapsed = self.silence = self.speech = 0.0
        self.started = False

    def step(self, voiced):
        self.elapsed += self.dt
        if voiced:
            self.started = True
            self.speech += self.dt
            self.silence = 0
        else:
            self.silence += self.dt
        if self.elapsed >= self.maximum: return 'too_long'
        if not self.started and self.elapsed >= self.start_timeout: return 'no_speech'
        if self.started and self.silence >= self.silence_limit: return 'complete' if self.speech >= 0.25 else 'no_speech'
        return None


class WakeInput:
    def __init__(self, voice_config):
        import numpy as np
        import sounddevice as sd
        self.np, self.sd = np, sd
        self.config = voice_config
        self.wake = voice_config.get('wake', {})
        from audio_gain import SpeechGain
        self.audio_gain = SpeechGain(voice_config.get('gain', {}))
        self.backend = self.wake.get('backend', 'openwakeword')
        if self.backend == 'openwakeword':
            from openwakeword.model import Model
            from openwakeword_trials import MODEL_DIR as OWW_DIR, MODEL_FILES
            for name in MODEL_FILES:
                if not (OWW_DIR/name).is_file(): raise FileNotFoundError('Run python openwakeword_trials.py --setup first')
            self.phrase = 'Hey Jarvis'
            print('Using pretrained Hey Jarvis; voice.wake.phrase applies only to sherpa.')
            self.oww = Model(wakeword_models=[str(OWW_DIR/MODEL_FILES[0])],inference_framework='onnx',
                melspec_model_path=str(OWW_DIR/MODEL_FILES[1]),embedding_model_path=str(OWW_DIR/MODEL_FILES[2]),ncpu=1)
            return
        if self.backend != 'sherpa': raise ValueError('wake.backend must be openwakeword or sherpa')
        import sherpa_onnx
        import sentencepiece as spm
        self.phrase = self.wake.get('phrase', 'Hey Sitara').strip()
        if not self.phrase or '\n' in self.phrase: raise ValueError('Wake phrase must be one nonempty line')
        required = [MODEL_DIR / (part + '-' + SUFFIX) for part in ('encoder','decoder','joiner')] + [MODEL_DIR/'tokens.txt',MODEL_DIR/'bpe.model']
        for p in required:
            if not p.is_file(): raise FileNotFoundError(f'{p.name} missing. Run python setup_wake.py first.')
        tokenizer = spm.SentencePieceProcessor(model_file=str(MODEL_DIR/'bpe.model'))
        pieces = tokenizer.encode(self.phrase.upper(), out_type=str)
        known = {line.rsplit(' ',1)[0] for line in (MODEL_DIR/'tokens.txt').read_text(encoding='utf-8').splitlines()}
        if not pieces or any(t not in known or t == '<unk>' for t in pieces):
            raise ValueError('Wake phrase contains unsupported tokens; use an English phrase.')
        keywords = MODEL_DIR/'sitara-keywords.txt'
        keywords.write_text(' '.join(pieces) + '\n', encoding='utf-8')
        self.spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(MODEL_DIR/'tokens.txt'), encoder=str(required[0]), decoder=str(required[1]), joiner=str(required[2]),
            keywords_file=str(keywords), num_threads=2, provider='cpu',
            keywords_score=float(self.wake.get('score',1.5)), keywords_threshold=float(self.wake.get('threshold',0.35)),
            num_trailing_blanks=1)

    def wait(self):
        if self.backend == 'openwakeword': return self.wait_openwakeword()
        stream = self.spotter.create_stream()
        print(f'Listening for "{self.phrase}" (Ctrl+C to stop)...')
        last_meter = time.monotonic()
        with self.sd.InputStream(channels=1, dtype='float32', samplerate=16000, device=self.config.get('input_device')) as mic:
            while True:
                samples, overflow = mic.read(1600)
                if overflow: raise RuntimeError('Microphone overflow during wake detection; check CPU/audio device')
                if self.wake.get('diagnostics', False) and time.monotonic()-last_meter >= 2:
                    print(f'Microphone RMS: {float(self.np.sqrt(self.np.mean(samples**2))):.4f}', flush=True)
                    last_meter = time.monotonic()
                stream.accept_waveform(16000, self.audio_gain.process_float(samples.reshape(-1)))
                while self.spotter.is_ready(stream):
                    self.spotter.decode_stream(stream)
                    result = self.spotter.get_result(stream)
                    if result:
                        print(f"Wake detected: {result}", flush=True)
                        self.spotter.reset_stream(stream)
                        return str(result)

    def wait_openwakeword(self):
        from audio_gain import SpeechGain
        self.audio_gain = SpeechGain(self.config.get('gain', {}))
        self.oww.reset()
        # Independent threshold: existing sherpa threshold is not reused.
        threshold=float(self.wake.get('openwakeword_threshold',0.5))
        print(f'Listening for "{self.phrase}" with openWakeWord...',flush=True)
        last_meter=time.monotonic()
        with self.sd.InputStream(channels=1,dtype='int16',samplerate=16000,device=self.config.get('input_device')) as mic:
            while True:
                samples,overflow=mic.read(1280)
                if overflow: raise RuntimeError('Microphone overflow during wake detection')
                enhanced=self.audio_gain.process_pcm(samples.reshape(-1))
                scores=self.oww.predict(enhanced)
                score=max((float(v) for v in scores.values()),default=0.0)
                if self.wake.get('diagnostics',False) and time.monotonic()-last_meter>=2:
                    print(f'Speech level: {self.audio_gain.level_dbfs}; gain: {self.audio_gain.gain:.2f}x; wake score: {score:.3f}',flush=True)
                    last_meter=time.monotonic()
                if score>=threshold:
                    print(f'Wake detected: Hey Jarvis ({score:.3f})',flush=True)
                    return 'HEY JARVIS'

    def cue(self):
        # Detector microphone is already closed, so it cannot hear this tone.
        rate = 24000
        count = int(rate*0.25)
        t = self.np.arange(count)/rate
        volume = max(0, min(0.8, float(self.wake.get('cue_volume',0.35))))
        fade = self.np.minimum(1, self.np.minimum(t/0.01,(0.25-t)/0.01))
        tone = (volume*fade*self.np.sin(2*self.np.pi*880*t)).astype('float32')
        print('Playing listening cue...', flush=True)
        try:
            self.sd.play(tone,rate,device=self.config.get('output_device')); self.sd.wait()
        except Exception as exc:
            print(f'Listening cue failed: {exc}', flush=True)


    def capture(self):
        import webrtcvad
        vad = webrtcvad.Vad(2)
        from audio_gain import SpeechGain
        gain = SpeechGain(self.config.get('gain', {}))
        boundary = CommandBoundary(start_timeout=float(self.wake.get('command_start_timeout',5)),
                                   silence_seconds=float(self.wake.get('command_silence_seconds',0.9)),
                                   maximum=float(self.config.get('max_recording_seconds',15)))
        frames = []
        print('Speak your command now...')
        with self.sd.InputStream(channels=1,dtype='int16',samplerate=16000,device=self.config.get('input_device')) as mic:
            while True:
                samples, overflow = mic.read(480)
                if overflow: raise RuntimeError('Microphone overflow; command discarded')
                data = samples.reshape(-1)
                frames.append(gain.process_pcm(data))
                outcome = boundary.step(vad.is_speech(data.tobytes(),16000))
                if outcome:
                    if outcome != 'complete':
                        print('Command discarded:',outcome)
                        return None, {'cancelled':True,'reason':outcome}
                    return self.np.concatenate(frames).astype('float32') / 32768.0, {'audio_seconds':round(boundary.elapsed,3)}

    def listen(self, voice, on_wake=None):
        self.wait()
        detected_at = time.monotonic()
        pause_start=time.monotonic()
        if on_wake is not None: on_wake()
        pause_seconds=time.monotonic()-pause_start
        cue_start=time.monotonic()
        self.cue()
        cue_seconds = time.monotonic()-cue_start
        waveform, timing = self.capture()
        timing['cue_s'] = round(cue_seconds,3)
        timing['wake_pause_s'] = round(pause_seconds,3)
        if waveform is None: return '', timing
        started = time.monotonic()
        segments, _ = voice.asr.transcribe(waveform,language='en',beam_size=1,vad_filter=True,condition_on_previous_text=False)
        text = ' '.join(s.text.strip() for s in segments).strip()
        return text, {**timing,'asr_seconds':round(time.monotonic()-started,3),'wake_phrase':self.phrase,'wake_to_transcript_s':round(time.monotonic()-detected_at,3)}
