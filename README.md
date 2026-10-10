# Treadmill Browser Assistant

A local voice/typed assistant for controlling YouTube in Chrome. Current revision: **0.4.1-error-resume-beta**, extending the verified **0.1.0-ptt** baseline. Voice recognition uses Whisper tiny.en (faster-whisper CPU int8); command interpretation uses Ollama Qwen3-1.7B; short spoken announcements use the lightweight KittenTTS nano int8 model.

This revision adds experimental local **Hey Jarvis** activation. Start with stationary tests, including background YouTube audio, before treadmill testing. F8 push-to-talk remains available for stationary fallback.

## Wake pause and concurrent announcements

Wake pause now uses a direct injected playback operation, verifies the paused state, and prints `Wake pause result` with the target tab URL or failure reason. This bypasses stale content-script message handlers.

On wake detection, the assistant asks YouTube to pause its current playing video before the cue and command capture. This requires a connected Controller tab and does not improve wake detection itself. Playback restores after the interaction for volume, scroll, shuffle, seek or cancelled/error commands, only if the original video and page still match. Explicit play/pause, next/previous, selecting a video/playlist and navigation take ownership of playback and suppress automatic resume, only after successful actions; failed or timed-out commands restore the original matching video. A 60-second browser fallback restores a matching paused video if the assistant disconnects before cleanup.

Browser commands are queued before spoken announcements start on a separate thread. Speech and browser execution overlap; the microphone reopens only after speech finishes. An announcement describes the intended action; browser errors are spoken afterward. Existing diagnostic timings distinguish browser completion from speech completion.

Reload the extension in chrome://extensions, refresh YouTube and reopen the Controller tab after copying this update. Run `python assistant.py --wake --no-debug` to avoid optional screenshots and diagnostic delays.

## Continue and unsupported commands

“Continue”, “resume”, and common current-video variants directly resume playback without asking the LLM. Unsupported commands are instructed to return `resume_current`, which plays the current video without navigation. A guard rejects model-generated scrolling without explicit scroll/page wording. The Controller also has a Continue current video button. Open a fresh Controller tab after reloading extension version 1.14.2. Unknown-command classification still depends on the model for instructions outside the direct rules; it is not guaranteed to recognise every unsupported request.

## Direct playback fix

Direct continue/resume phrases skip optional before/after snapshots even in debug mode. Play, pause and seek use an injected browser operation independent of the content script, and verify play/pause state. Navigation and numbering still use the content script. Reload extension 1.14.3 and reopen the Controller tab. `--no-debug` also disables optional snapshots for other commands.

## Productionization stage 1: explicit local model loading

Keep personal config.json and existing models. No new config keys are required; voice.model_dir defaults to models/voice relative to this project. In your activated Conda environment, run:

```bat
python setup_models.py
python setup_models.py --check
python assistant.py --wake --no-debug
```

Setup is the only voice-model download step. It prepares Whisper tiny.en, the configured KittenTTS ONNX nano model, and the existing Hey Jarvis wake files. Existing Hugging Face caches can be reused by the downloader; a one-time anonymous-download warning during setup is possible. `--check` only validates local files and makes no downloads. `--voice-only` omits wake model setup/check. Explicit sherpa users still use setup_wake.py.

Normal voice startup requires prepared files and loads local folders in offline mode. Missing files or changed model IDs produce a setup instruction instead of a silent download. Set tts_enabled=false to run without preparing KittenTTS. These checks verify required file presence, not model integrity. Normal startup needs no Hugging Face connection; YouTube still needs internet and Ollama must remain available locally.

Do not commit models/ or config.json. Automatic Controller startup, connection recovery and a Windows installer are subsequent stages, not included here. Model downloads and physical Windows inference have not been exercised in this build environment; verify on your current Conda install before committing this stage.

## Error cleanup

Temporary wake pauses now restore after browser errors, timeouts, command interpretation errors or cancelled capture. Cleanup runs before error speech for known failures and again on final exit if needed. Successful pause/play, selection, next/previous or navigation still owns playback. The browser only restores the original matching page/player/source, so failed navigation cannot accidentally start another video. A disconnected Controller can prevent immediate cleanup; the terminal reports that limitation.

## Current capabilities

- Search YouTube, scroll, choose videos by blue number, control playback and volume.
- Number homepage/search videos and ordinary watch-page recommendations.
- List loaded playlists with matching purple numbers and titles; select playlists by number or name and start playback.
- Number songs on playlist pages and in the watch-page playlist panel; select a visible numbered song within the playlist.
- Next/previous playlist controls and shuffle toggle.
- Local microphone input, printed transcripts, intended-action speech and spoken browser errors; typed mode remains available.
- Browser snapshots, screenshots, raw model output, deterministic corrections and rolling retention of the latest 100 interactions.

The user verified playlist names/indices, playlist playback, shuffle and song selection/switching, as well as voice recognition, command execution and spoken announcements. Recognition was better with the Plantronics headset than the Sony Bluetooth headset. Performance under treadmill noise is not yet verified.

## OpenWakeWord and automatic speech gain (new)

Preferred experimental backend is now **openWakeWord / Hey Jarvis**, based on the user's comparison. Existing typed/F8 modes and optional sherpa backend are retained. This is a test revision, not a validated treadmill release.

Copy updates over your checkout, preserving `.git`, `LICENSE` and personal `config.json`. Then, in your active Conda environment:

```bat
python -m pip install -r requirements-openwakeword.txt
python openwakeword_trials.py --setup
python openwakeword_trials.py --condition playing
```

The same 10-attempt, five-second test now applies automatic speech gain by default. Say **Hey Jarvis**. Use `--no-agc` to compare against the previous unamplified behavior. Keep the 0.5 threshold unchanged while checking the effect of gain. Results include gain settings and per-trial input/output levels, effective gain after limiting, and limiter counts. Above-floor audio includes noise; these levels are not speech SNR. Gain now uses original audio level without requiring VAD recognition. Noise above the floor may also be boosted. Detector buffers and gain state reset per trial.

For full commands:

```bat
python assistant.py --wake --no-debug
```

Say Hey Jarvis, wait for the beep, then give a command. The default backend is openWakeWord even for old configs that lack `backend`; its pretrained phrase is fixed to Hey Jarvis. The old `phrase`/`score`/`threshold` settings apply only if `voice.wake.backend` is explicitly `sherpa`. OpenWakeWord uses its separate `openwakeword_threshold`, default 0.5.

Add/merge these sections into your existing `voice` settings, preserving audio device IDs and other settings:

```json
"gain": {
  "enabled": true,
  "target_dbfs": -24,
  "max_gain_db": 18,
  "minimum_dbfs": -60
},
"wake": {
  "backend": "openwakeword",
  "openwakeword_threshold": 0.5,
  "command_start_timeout": 10,
  "command_silence_seconds": 1.5,
  "diagnostics": false
}
```

Old configs use AGC defaults but retain their existing command timeout values. Increase those explicitly if desired. Enable `wake.diagnostics` to print estimated above-floor audio dBFS, nominal gain and wake scores every two seconds in full-assistant mode.

Gain control measures original 10 ms frames above -60 dBFS, averages up to 50 qualifying frames, and boosts toward -24 dBFS up to +18 dB (about 8x). It no longer requires a speech detector to recognise quiet speech first. Gain ramps over time and output peaks are limited to 0.95. Below-floor audio makes gain decay toward unity. Above-floor noise can also be amplified. These are digital audio levels, not dB SPL or speech SNR; gain does not restore removed speech detail.

Gain is applied before openWakeWord and to captured command audio before Whisper, including F8 input. Raw hardware-device gain/settings are unchanged. `voice.gain.enabled=false` disables amplification in full mode. WebRTC VAD is installed by the new requirements file.

The existing openWakeWord model files from the comparison script are reused. No custom-model training is needed. Supplied pretrained openWakeWord wake models are CC BY-NC-SA 4.0; the framework code is Apache-2.0. This ZIP does not bundle model weights or change your repository's license.

Validation: 32 logic tests pass, including effective gain measurements, recognition-independent boosting, gain limits, below-floor gating, silence, clipping protection, PCM conversion and disabled gain. Python compilation and extension syntax checks pass. Five mocked browser pause/resume scenarios passed (restore, explicit playback ownership, already paused, changed video and expired pause). Acoustic improvements and false-trigger rate have not been measured; run the comparison on your headset before committing this as a working release.

## Requirements

- Windows and Chrome; Python 3.11, preferably in an activated Conda environment.
- Ollama installed and running locally, with `qwen3:1.7b` downloaded (`ollama pull qwen3:1.7b`).
- A microphone and playback device. A headset is useful for reducing audio interference.
- Internet for package installation and first model downloads. Inference runs locally after downloads. YouTube itself needs internet.

Dependency files contain compatibility ranges, not a fully pinned lockfile. The user's working installed versions were not supplied. Preserve your known-good environment; dependency upgrades need retesting.

## Setup with Conda (recommended for the existing installation)

Activate your Python 3.11 environment, then open this project directory:

```bat
conda activate YOUR_ENV_NAME
cd /d "C:\path\to\treadmill_assistant"
python --version
python -m pip install -r requirements-voice.txt
```

For typed-only use, install `requirements.txt` instead. Voice dependencies are optional in typed mode.

Alternatively, run `setup_voice.bat` from a terminal with Python 3.11 active. It creates a separate `.venv` and installs voice dependencies there. It uses `python`, so the Windows `py` launcher is not required. `test_voice.bat` and `start_voice.bat` prefer that `.venv` when present, otherwise use the active terminal's Python.

## Configuration and audio devices

The package uses `config.example.json` if `config.json` does not exist. Make a personal copy before changing devices/settings:

```bat
copy config.example.json config.json
python voice_devices.py
```

`config.json` is ignored by Git. The sample contains only portable defaults. In its `voice` section:

- `input_device`: microphone device ID; `null` uses the audio library's default input.
- `output_device`: speaker/headphone device ID; `null` uses its default output.
- Input and output defaults are independent. Set both explicitly to use one headset. IDs may change after reconnecting devices; rerun `voice_devices.py` if necessary.
- `ptt_key`: defaults to `f8`; `max_recording_seconds`: defaults to 15.
- `tts_enabled`: set false to disable speech output.
- `tts_model`: explicitly selects `KittenML/kitten-tts-nano-0.8-int8`, avoiding KittenTTS's larger default model; default voice is Bruno.

## Chrome extension and Controller

1. Open `chrome://extensions`, enable Developer mode, select **Load unpacked**, and choose this project's `extension` directory.
2. Remove/disable an older duplicate Treadmill extension. Existing working v14/v15 extension code is unchanged in this release, so replacing it is optional if it is already installed.
3. Refresh existing YouTube tabs and sign in to YouTube for your library.
4. Click the extension toolbar icon to open **Treadmill Controller**. Keep this tab open; it can remain in the background. The `chrome://extensions` settings tab does not need to stay open.
5. Keep Ollama running, then start the assistant as below.

The extension uses a Controller tab to poll the local Flask server (default port 8765). This release does not automatically open, recover or verify the Controller at startup. The startup voice message confirms voice loading, not browser connectivity. Extension permissions include broad host access for existing screenshot/tab functionality; review `extension/manifest.json` before distribution.

## Test and run

First test microphone and speakers while stationary:

```bat
python test_voice.py
```

Wait for the initial model downloads and spoken prompt. Hold F8, speak a short sentence, then release. Check the transcript and spoken readback. This test does not execute browser commands.

Start voice commands:

```bat
python assistant.py --voice
```

Or use typed commands:

```bat
python assistant.py
```

Example commands: "pause the video", "search YouTube for speculative decoding", "show me my playlists", "play playlist six", "play song number three", "next song", "shuffle the playlist".

In voice mode, F8 is monitored only while waiting for a command. Microphone capture begins after key press and stops on release; listening is inactive during TTS and action execution. Escape cancels the pending recording; Ctrl+C exits. Recordings longer than 15 seconds are discarded. Very short/quiet recordings are ignored. Keys are not suppressed, so avoid another focused application that binds F8.

Announcements describe intended actions before execution. Browser errors are spoken afterward. Raw microphone audio is not saved; transcripts and timing enter the existing diagnostic logs. First model loading may take time. TTS failures are printed and do not prevent ASR use; voice initialization errors leave typed mode available via a separate invocation.

## Try Hey Sitara (new)

From your activated Python 3.11 Conda environment, in the project directory:

```bat
python -m pip install -r requirements-wake.txt
python setup_wake.py
python test_wake.py
```

`setup_wake.py` downloads the official English GigaSpeech 3.3M keyword-spotting model once into the Git-ignored `models` folder. `test_wake.py` loads only the detector: say **Hey Sitara**, then check for a printed detection and beep. It never executes browser commands. Test repeated activations and ordinary speech/YouTube audio for false detections. Ctrl+C exits.

Once detection works, start the full assistant with Ollama and Controller open:

```bat
python assistant.py --wake
```

Say **Hey Assistant**, **wait for the beep**, then say your command and stop speaking. This first implementation uses separate wake and command phases; saying the whole command immediately after the name can lose its beginning. Detection stops during the beep, command capture, transcription, browser execution and TTS. A fresh detector stream is created for each listening phase so old buffered audio cannot retrigger it.

Command capture uses WebRTC VAD. It ends after 0.9 seconds of silence, cancels if speech does not begin within 5 seconds, and discards a recording exceeding the configured 15-second limit. Noise/audio overflows can cause cancellation; these are reported. Background speech can still activate the detector and ASR; headset use and stationary false-trigger testing are essential.

Optional settings under `voice.wake` in your local `config.json`:

```json
"wake": {
  "phrase": "Hey Assistant",
  "score": 2.0,
  "threshold": 0.20,
  "command_start_timeout": 5,
  "command_silence_seconds": 0.9
}
```

The updated sample uses Hey Assistant because user testing found Sitara difficult to detect. Existing local configs are preserved; without a wake block, code still defaults to Hey Sitara. Set your local phrase explicitly. Existing local configs without the other settings use code defaults and retain your selected microphone/output. Changing `phrase` and restarting automatically regenerates the keyword tokens from the model's tokenizer; no detector retraining is required. New names still need pronunciation tests. Higher threshold makes triggering harder; higher score boosts the keyword path. Defaults are starting values, not tuned settings for your headset.

To update an existing Git checkout, copy the new source files over it while preserving `.git`, your `LICENSE`, personal `config.json` and `.venv`. This ZIP contains no Git history or license and does not push to your remote. Keep the known-good baseline tag until wake testing succeeds.

Run logic checks with `python -m unittest discover -s tests`. These validate capture cancellation, silence endpointing and ASR handoff; they do not measure acoustic accuracy.

## Cue and latency diagnostics (0.2.1)

Keep your working local `config.json` and its Hey Assistant phrase. Copy source updates over your checkout without replacing `.git`, `LICENSE` or personal settings.

Run without diagnostic snapshots, screenshots or persistent logs:

```bat
python assistant.py --wake --no-debug
```

This keeps browser execution and its required state checks. It also skips the optional post-navigation snapshot delay. No existing logs are deleted. Console transcripts, errors and timing summaries remain visible. You can alternatively set top-level `"debug_mode": false` in `config.json`; default is true. `--no-debug` overrides true.

Wake detection now prints **Wake detected** immediately, before attempting the cue. The cue is a 250 ms tone at 24 kHz with a fade and higher amplitude. Configure `voice.wake.cue_volume` (default 0.35, max 0.8); output uses your selected output device. Playback failures are printed and command capture continues. A successful audio-library call does not prove you heard it, so test output/system volume if the message appears without audible sound. Capture begins after the cue finishes.

For microphone-level diagnostics, set `voice.wake.diagnostics` to true; an RMS level prints every two seconds while waiting. This is optional console output and can be used in `test_wake.py` too.

**Action timing** prints after the browser result: captured audio duration, cue/ASR timings, wake-to-transcript time, pre-snapshot, model interpretation, spoken announcement and browser action. **Ready timing** also includes result speech and post-snapshot. `transcript_to_browser_result_s` starts after transcription and ends when the browser response arrives; it is not an exact visual-action timestamp. Browser action timing includes waiting for completion/verification. Compare identical commands with and without debug mode. Speech generation and playback remain synchronous and their full duration appears under announcement/result speech.

The 10-second user-observed delay is not yet attributed to a particular stage. No-debug performance, new cue audibility and normal-pace wake recognition need user testing.

## Known limitations

- "Previous song" after shuffle was observed to restart the current song. Its cause has not been established; compare with YouTube's native Previous button. Reliable back-one-track behavior remains a follow-up.
- Shuffle is a toggle, not an explicit enabled/disabled setter.
- Named playlist selection exists; named song selection and add/remove playlist entries do not.
- Numbering/listing represents loaded content, not every account item. Numbered songs must be visible to select through the existing command. Further scrolling may be needed.
- Wake phrase is experimental; automatic Controller startup and connection heartbeat are not implemented.
- Diagnostic snapshots and synchronous speech can add latency. Packaging alone does not remove these waits.
- ASR can misrecognize speech, particularly with poor microphones or background media. Do not treat the stationary test build as a hands-free treadmill release.

## Feature backlog

Desired playlist interface:

| Action | Status / planned behavior |
| --- | --- |
| `list_playlists()` | Existing `show_playlists` implementation; align naming later |
| `play_playlist(name)` | Implemented; numbered selection also available |
| `next_track()` | Existing next playlist control; align naming and independently verify |
| `previous_track()` | Existing previous control; resolve restart behavior |
| `shuffle_playlist(enabled)` | Replace toggle with verified explicit state |
| `play_playlist_track(name)` | Resolve within active playlist; clarify duplicate names |
| `add_to_playlist(video, playlist)` | Resolve exact targets, avoid duplicates, verify addition |
| `remove_from_playlist(video, playlist)` | Resolve exact targets, clarify ambiguity, verify intended removal |

Next release priorities:

1. Test and tune the new wake phrase/VAD against misses and false triggers from YouTube/treadmill noise. Detection is suspended during assistant speech, but background speech can still trigger it.
2. Automatically start/open Controller, verify connection before announcing Ready, and announce disconnections.
3. Test headset recognition and latency with treadmill noise before running hands-free.
4. Measure runtime delays with the new debug switch and stage timings, then optimize the measured bottleneck.
5. Add/remove songs and remaining playlist refinements; improve Windows launch/setup packaging.

## Repository use

The ZIP contains source only: no virtual environment, model weights, diagnostics, machine configuration or Git history. `VERSION` identifies this baseline. Keep `.gitignore` in the repository; do not force-add local `config.json`, logs or screenshots.

To create a local repository from this folder:

```bat
git init
git add .
git commit -m "Working push-to-talk YouTube assistant baseline"
git tag v0.4.1-error-resume-beta
```

No remote repository is created or pushed by these commands. No project license has been selected; choose one before publishing for reuse.

## Validation and implementation references

Python compilation and extension JavaScript syntax checks passed. Mocked tests exercised delayed playlist rendering, playlist playback success/failure, F8 capture/release, transcription timing, TTS playback and nonfatal TTS errors. User testing established the working behavior noted above. Dependency installation on a fresh Windows environment and physical audio were not tested by the build environment. This revision adds optional wake/VAD input while preserving browser routing and existing input modes. Eight hardware-independent wake/capture/debug regression tests pass. Actual sherpa model download/loading, Windows package installation and wake recognition have not been tested in the build environment.

- https://github.com/SYSTRAN/faster-whisper
- https://github.com/KittenML/KittenTTS
- https://github.com/KittenML/KittenTTS/blob/main/example_onnx_0.8.py
- https://python-sounddevice.readthedocs.io/en/latest/api/streams.html

Wake implementation references:
- https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html
- https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/keyword-spotter-from-microphone.py
