# Treadmill Browser Assistant

A local voice/typed assistant for controlling YouTube in Chrome. Working baseline: **0.1.0-ptt**, derived from v15. Voice recognition uses Whisper tiny.en (faster-whisper CPU int8); command interpretation uses Ollama Qwen3-1.7B; short spoken announcements use the lightweight KittenTTS nano int8 model.

This release supports **stationary push-to-talk testing**. Wake-phrase activation is required before hands-free treadmill use. Hold F8 to speak and release to submit; do not use keyboard controls while running.

## Current capabilities

- Search YouTube, scroll, choose videos by blue number, control playback and volume.
- Number homepage/search videos and ordinary watch-page recommendations.
- List loaded playlists with matching purple numbers and titles; select playlists by number or name and start playback.
- Number songs on playlist pages and in the watch-page playlist panel; select a visible numbered song within the playlist.
- Next/previous playlist controls and shuffle toggle.
- Local microphone input, printed transcripts, intended-action speech and spoken browser errors; typed mode remains available.
- Browser snapshots, screenshots, raw model output, deterministic corrections and rolling retention of the latest 100 interactions.

The user verified playlist names/indices, playlist playback, shuffle and song selection/switching, as well as voice recognition, command execution and spoken announcements. Recognition was better with the Plantronics headset than the Sony Bluetooth headset. Performance under treadmill noise is not yet verified.

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

## Known limitations

- "Previous song" after shuffle was observed to restart the current song. Its cause has not been established; compare with YouTube's native Previous button. Reliable back-one-track behavior remains a follow-up.
- Shuffle is a toggle, not an explicit enabled/disabled setter.
- Named playlist selection exists; named song selection and add/remove playlist entries do not.
- Numbering/listing represents loaded content, not every account item. Numbered songs must be visible to select through the existing command. Further scrolling may be needed.
- No wake phrase, automatic Controller startup, connection heartbeat or debug-mode switch yet.
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

1. Replace stationary push-to-talk with wake phrase/VAD; prevent YouTube audio and assistant speech from triggering commands.
2. Automatically start/open Controller, verify connection before announcing Ready, and announce disconnections.
3. Test headset recognition and latency with treadmill noise before running hands-free.
4. Add `debug_mode`: diagnostics on/off while preserving execution state and user-facing errors. Retain 100 interactions when enabled.
5. Add/remove songs and remaining playlist refinements; improve Windows launch/setup packaging.

## Repository use

The ZIP contains source only: no virtual environment, model weights, diagnostics, machine configuration or Git history. `VERSION` identifies this baseline. Keep `.gitignore` in the repository; do not force-add local `config.json`, logs or screenshots.

To create a local repository from this folder:

```bat
git init
git add .
git commit -m "Working push-to-talk YouTube assistant baseline"
git tag v0.1.0-ptt
```

No remote repository is created or pushed by these commands. No project license has been selected; choose one before publishing for reuse.

## Validation and implementation references

Python compilation and extension JavaScript syntax checks passed. Mocked tests exercised delayed playlist rendering, playlist playback success/failure, F8 capture/release, transcription timing, TTS playback and nonfatal TTS errors. User testing established the working behavior noted above. Dependency installation on a fresh Windows environment and physical audio were not tested by the build environment. This cleanup changes configuration fallback and launch scripts; functional browser/voice routing is preserved.

- https://github.com/SYSTRAN/faster-whisper
- https://github.com/KittenML/KittenTTS
- https://github.com/KittenML/KittenTTS/blob/main/example_onnx_0.8.py
- https://python-sounddevice.readthedocs.io/en/latest/api/streams.html
