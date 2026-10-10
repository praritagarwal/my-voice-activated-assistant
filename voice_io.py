"""Local voice I/O. Capture is separate from routing so wake-word input can replace it."""
import threading
import time


class VoiceIO:
    def __init__(self, config):
        from local_models import local_model_path, enable_offline_loading
        asr_path=local_model_path(config,'whisper')
        tts_path=local_model_path(config,'kitten') if config.get('tts_enabled',True) else None
        enable_offline_loading()
        import numpy as np
        import sounddevice as sd
        from faster_whisper import WhisperModel
        from pynput import keyboard
        self.np, self.sd, self.keyboard = np, sd, keyboard
        self.config = config
        self.tts = None
        print('Loading local Whisper:', asr_path)
        self.asr = WhisperModel(str(asr_path), device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)
        if config.get('tts_enabled', True):
            try:
                from kittenml import KittenTTS
                print('Loading local KittenTTS:', tts_path)
                self.tts = KittenTTS(str(tts_path))
            except Exception as exc:
                print(f'TTS unavailable: {exc}. Voice input remains available.')

    def speak(self, text):
        if self.tts is None:
            return
        try:
            audio = self.tts.generate(text, voice=self.config.get('tts_voice', 'Bruno'))
            self.sd.play(audio, getattr(self.tts, 'sample_rate', 24000), device=self.config.get('output_device'))
            self.sd.wait()
        except Exception as exc:
            print(f'TTS error: {exc}')

    def listen(self):
        """Hold F8 to record; release to transcribe. Escape cancels. No mic outside capture."""
        down, done, cancelled = threading.Event(), threading.Event(), threading.Event()
        chunks, statuses = [], []
        key = getattr(self.keyboard.Key, self.config.get('ptt_key', 'f8'))
        max_seconds = float(self.config.get('max_recording_seconds', 15))
        def press(k):
            if k == self.keyboard.Key.esc:
                cancelled.set(); done.set(); return False
            if k == key and not done.is_set():
                down.set()
        def release(k):
            if k == key and down.is_set():
                down.clear(); done.set(); return False
        def audio(data, frames, timing, status):
            if status:
                statuses.append(str(status))
            if down.is_set() and not done.is_set():
                chunks.append(data.copy())
        print(f'Hold {self.config.get("ptt_key", "f8").upper()} while speaking; release to send. Esc cancels.')
        # Listener exists only during listen(): it cannot retrigger during TTS/actions.
        listener = self.keyboard.Listener(on_press=press, on_release=release)
        listener.start()
        try:
            while not down.wait(0.05):
                if done.is_set(): return '', {'cancelled': True}
                if not listener.is_alive(): raise RuntimeError('Push-to-talk keyboard listener stopped')
            with self.sd.InputStream(samplerate=16000, channels=1, dtype='float32', device=self.config.get('input_device'), callback=audio):
                started = time.monotonic()
                while not done.wait(0.05):
                    if time.monotonic() - started >= max_seconds:
                        cancelled.set(); done.set()
                        print('Recording too long; command cancelled. Release the key and retry.')
        finally:
            listener.stop(); listener.join(timeout=1)
        if cancelled.is_set() or not chunks:
            return '', {'cancelled': True, 'audio_status': statuses}
        waveform = self.np.concatenate(chunks).reshape(-1)
        seconds = len(waveform) / 16000
        if seconds < 0.25 or float(self.np.sqrt(self.np.mean(waveform ** 2))) < 0.002:
            print('No clear speech captured.'); return '', {'audio_seconds': seconds, 'empty': True}
        started = time.monotonic()
        from audio_gain import SpeechGain
        gain=SpeechGain(self.config.get('gain', {}))
        waveform=self.np.concatenate([gain.process_float(waveform[i:i+480]) for i in range(0,len(waveform),480)])
        segments, _ = self.asr.transcribe(waveform, language='en', beam_size=1, vad_filter=True, condition_on_previous_text=False)
        text = ' '.join(s.text.strip() for s in segments).strip()
        return text, {'audio_seconds': round(seconds, 3), 'asr_seconds': round(time.monotonic()-started, 3), 'audio_status': statuses}


def action_announcement(command):
    tool = command.get('tool')
    if tool == 'resume_current': return 'I did not recognise that action. Resuming the current video.'
    if tool == 'youtube_search': return 'Searching YouTube for ' + command['query']
    if tool == 'show_playlists': return 'Listing your playlists.'
    if tool == 'play_playlist': return 'Opening playlist ' + str(command.get('name', command.get('index', '')))
    if tool == 'play_video': return 'Selecting video ' + str(command.get('visible_index', ''))
    if tool == 'playlist_control': return {'next':'Going to the next song.', 'previous':'Going to the previous song.', 'shuffle':'Toggling shuffle.'}.get(command.get('action'), 'Controlling the playlist.')
    if tool == 'media_control': return {'play':'Resuming playback.', 'pause':'Pausing playback.', 'seek_forward':'Skipping forward.', 'seek_backward':'Skipping backward.'}.get(command.get('action'), 'Controlling playback.')
    if tool == 'set_volume': return f"Setting volume to {command['percentage']} percent."
    if tool == 'scroll_page': return 'Scrolling ' + command['direction']
    return 'Executing your command.'
