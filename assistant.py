"""Local Qwen tool router for the Treadmill Chrome Controller extension.

Run with: python assistant.py
The Chrome controller page long-polls GET /next for validated browser commands.
"""

import json
import argparse
import sys
import re
import queue
import threading
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, request

import logging
import time
import uuid
import base64
import shutil
from datetime import datetime, timezone

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
CONFIG_SOURCE = CONFIG_PATH if CONFIG_PATH.exists() else CONFIG_PATH.with_name("config.example.json")
CONFIG = json.loads(CONFIG_SOURCE.read_text(encoding="utf-8"))
DEBUG_MODE = bool(CONFIG.get("debug_mode", True)) and "--no-debug" not in sys.argv
COMMANDS: queue.Queue[dict[str, Any]] = queue.Queue()
APP = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
LOG_DIR = CONFIG_PATH.parent / "logs"
if DEBUG_MODE: LOG_DIR.mkdir(exist_ok=True)
SCREEN_DIR = LOG_DIR / "screenshots"
if DEBUG_MODE: SCREEN_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "interactions.jsonl"
MAX_INTERACTIONS = 100
LOG_LOCK = threading.Lock()
INTERACTIONS: dict[str, dict[str, Any]] = {}
INTERACTION_ORDER: list[str] = []

def _write_history() -> None:
    tmp = LOG_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for rid in INTERACTION_ORDER:
            handle.write(json.dumps(INTERACTIONS[rid], ensure_ascii=False) + "\n")
    tmp.replace(LOG_PATH)

def _load_history() -> None:
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                rid = entry["request_id"]
                if rid not in INTERACTIONS:
                    INTERACTION_ORDER.append(rid)
                INTERACTIONS[rid] = entry
            except (ValueError, KeyError, TypeError):
                continue
    while len(INTERACTION_ORDER) > MAX_INTERACTIONS:
        rid = INTERACTION_ORDER.pop(0)
        INTERACTIONS.pop(rid, None)
        shutil.rmtree(SCREEN_DIR / rid, ignore_errors=True)
    _write_history()

if DEBUG_MODE: _load_history()
RESULTS: dict[str, dict[str, Any]] = {}
RESULT_CONDITION = threading.Condition()

def log_event(request_id: str, event: str, **fields: Any) -> None:
    if not DEBUG_MODE: return
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    with LOG_LOCK:
        if request_id not in INTERACTIONS:
            INTERACTIONS[request_id] = {"request_id": request_id, "events": []}
            INTERACTION_ORDER.append(request_id)
        INTERACTIONS[request_id]["events"].append(record)
        while len(INTERACTION_ORDER) > MAX_INTERACTIONS:
            old = INTERACTION_ORDER.pop(0)
            INTERACTIONS.pop(old, None)
            shutil.rmtree(SCREEN_DIR / old, ignore_errors=True)
        _write_history()


def save_browser_state(request_id: str, phase: str, result: dict[str, Any]) -> dict[str, Any]:
    """Persist screenshot separately; keep structured state in the JSONL history."""
    data = dict(result)
    image_data = data.pop("screenshot_data_url", None)
    if isinstance(image_data, str) and image_data.startswith("data:image/png;base64,"):
        try:
            raw = base64.b64decode(image_data.split(",", 1)[1], validate=True)
            if len(raw) <= 8 * 1024 * 1024:
                folder = SCREEN_DIR / request_id
                folder.mkdir(exist_ok=True)
                target = folder / f"{phase}.png"
                target.write_bytes(raw)
                data["screenshot_path"] = str(target.relative_to(LOG_DIR))
            else:
                data["screenshot_error"] = "screenshot_too_large"
        except (ValueError, OSError) as exc:
            data["screenshot_error"] = str(exc)
    log_event(request_id, f"browser_state_{phase}", state=data)
    return data


def browser_snapshot(request_id: str, phase: str, timeout: float = 8.0) -> dict[str, Any]:
    if not DEBUG_MODE: return {"ok": True, "skipped": True}
    snapshot_id = f"{request_id}:{phase}"
    COMMANDS.put({"tool": "__snapshot", "request_id": snapshot_id})
    with RESULT_CONDITION:
        arrived = RESULT_CONDITION.wait_for(lambda: snapshot_id in RESULTS, timeout=timeout)
        result = RESULTS.pop(snapshot_id) if arrived else {"ok": False, "error": "snapshot_timeout"}
    return save_browser_state(request_id, phase, result)


SYSTEM_PROMPT = """You are a precise browser command interpreter. Convert each user instruction into exactly one JSON object, no Markdown or explanation.

Allowed commands:
- resume_current: {"tool":"resume_current"} (fallback for unrecognised/unsupported instructions; continue the current video without navigation)
- youtube_search: {"tool":"youtube_search","query":"search terms"}
- scroll_page: {"tool":"scroll_page","direction":"up"|"down","fraction":0.5|1}
- play_video: {"tool":"play_video","visible_index":1} (1-based visible result)
- media_control: {"tool":"media_control","action":"pause"|"play"|"seek_forward"|"seek_backward"}
- set_volume: {"tool":"set_volume","percentage":0..100}
- show_playlists: {"tool":"show_playlists"} (open and list your YouTube playlists; use for show, open, list, find my playlists)
- play_playlist: {"tool":"play_playlist","index":6} OR {"tool":"play_playlist","name":"playlist name"} (select a playlist, NOT previous/next track)
- playlist_control: {"tool":"playlist_control","action":"next"|"previous"|"shuffle"} (ONLY for controlling songs already playing; never for choosing a playlist)

INTERPRETATION RULES:
- Continue, resume, carry on, keep playing, and continue the video mean media_control action play. NEVER interpret these as scrolling or selecting another video.
- Scroll only when the instruction explicitly requests scrolling or moving the page.
- If the instruction does not match a supported action, return resume_current. Do not guess an unrelated action.

IMPORTANT FOR SEARCH:
- Extract the user's intended search phrase. Remove only instructional scaffolding such as 'search for', 'find', 'on YouTube', or 'in YouTube'.
- Preserve the user's actual search terms VERBATIM, including spelling, initials, word order, capitalization, acronyms, and proper names.
- NEVER autocorrect, paraphrase, translate, hallucinate, or replace a name with a more familiar word. For example 'A R Rahman' MUST remain 'A R Rahman', never 'a r haram'.
- Do not insert the command verb 'search' into the search query.
- For 'scroll down' or 'scroll up', use fraction 0.5 unless the user specifies a full page.
- Do not invent actions or unsupported fields.
- Before returning JSON, briefly check that the tool matches the request and every argument (especially video index and playlist name) exactly matches the user's words. Do not output reasoning; output only JSON.

Examples:
User: Continue.
Output: {"tool":"media_control","action":"play"}
User: resume the current video
Output: {"tool":"media_control","action":"play"}
User: tell me the weather
Output: {"tool":"resume_current"}
User: search A R Rahman songs in youtube
Output: {"tool":"youtube_search","query":"A R Rahman songs"}
User: search for a song called Take On Me on YouTube
Output: {"tool":"youtube_search","query":"Take On Me"}
User: find videos about speculative decoding
Output: {"tool":"youtube_search","query":"speculative decoding"}
User: scroll down
Output: {"tool":"scroll_page","direction":"down","fraction":0.5}
User: play the third video
Output: {"tool":"play_video","visible_index":3}
User: show me my YouTube playlists
Output: {"tool":"show_playlists"}
User: play song number eighteen
Output: {"tool":"play_video","visible_index":18}
User: play playlist number six
Output: {"tool":"play_playlist","index":6}
User: play my workout playlist
Output: {"tool":"play_playlist","name":"workout"}
"""


@APP.get("/next")
def next_command():
    """Return one pending command to the Chrome extension, if any."""
    try:
        wait_seconds = min(max(float(request.args.get("wait", 0)), 0), 25)
        command = COMMANDS.get(timeout=wait_seconds)
        if command["tool"] != "__snapshot":
            log_event(command["request_id"], "browser_dispatched", tool=command["tool"])
        return jsonify(command)
    except queue.Empty:
        return jsonify({})
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid wait parameter"}), 400


@APP.post("/result")
def receive_result():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("request_id"), str) or not isinstance(payload.get("result"), dict):
        return jsonify({"error":"invalid result"}), 400
    rid = payload["request_id"]
    result = payload["result"]
    if not rid.endswith(":before") and not rid.endswith(":after"):
        log_event(rid, "browser_result", result=result)
    with RESULT_CONDITION:
        RESULTS[rid] = result
        RESULT_CONDITION.notify_all()
    return jsonify({"ok": True})


# Extract explicit video indices independently of the LLM. No additional dependencies.
_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50, "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90}
for _w, _n in _UNITS.items():
    if _n >= 1:
        _ORDINALS.setdefault(_w + "th", _n)
for _w, _n in _TENS.items():
    for _unit, _v in _UNITS.items():
        if 1 <= _v <= 9:
            _ORDINALS[_w + " " + next((k for k, val in _ORDINALS.items() if val == _v and k not in _UNITS), _unit)] = _n + _v

def _parse_number(phrase: str) -> int | None:
    phrase = phrase.lower().strip().replace("-", " ")
    digit = re.fullmatch(r"#?(\d+)(?:st|nd|rd|th)?", phrase)
    if digit:
        return int(digit.group(1))
    if phrase in _ORDINALS:
        return _ORDINALS[phrase]
    if phrase in _UNITS:
        return _UNITS[phrase]
    if phrase in _TENS:
        return _TENS[phrase]
    words = phrase.split()
    if len(words) == 2 and words[0] in _TENS:
        if words[1] in _UNITS and 1 <= _UNITS[words[1]] <= 9:
            return _TENS[words[0]] + _UNITS[words[1]]
        if words[1] in _ORDINALS and 1 <= _ORDINALS[words[1]] <= 9:
            return _TENS[words[0]] + _ORDINALS[words[1]]
    return None

_NUMBER_TOKEN = r"(?:#?\d+(?:st|nd|rd|th)?|[a-z]+(?:[- ][a-z]+)?)"

def extract_video_index(user_text: str) -> int | None:
    text = user_text.lower().strip()
    # Only interpret an index in an explicit selection instruction, not a title/year.
    if not re.search(r"\b(?:play|select|choose|open|click)\b", text):
        return None
    patterns = [
        rf"\b(?:video|song|track|result)\s*(?:number|no\.?|#)?\s*({_NUMBER_TOKEN})\b",
        rf"\b(?:play|select|choose|open|click)\s+(?:the\s+)?(?:number|#)\s*({_NUMBER_TOKEN})\b",
        rf"\b(?:play|select|choose|open|click)\s+(?:the\s+)?({_NUMBER_TOKEN})\s+(?:video|song|track|result)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            number = _parse_number(match.group(1))
            if number is not None and number > 0:
                return number
    return None

def extract_playlist_index(user_text: str) -> int | None:
    text = user_text.lower().strip()
    if not re.search(r"\b(?:play|open|start|select|choose)\b", text):
        return None
    patterns = [
        rf"\bplaylist\s*(?:number|no\.?|#)?\s*({_NUMBER_TOKEN})\b",
        rf"\b(?:the\s+)?({_NUMBER_TOKEN})\s+playlist\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            index = _parse_number(match.group(1))
            if index is not None and index > 0:
                return index
    return None

def correct_playlist_selection(user_text: str, command: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    index = extract_playlist_index(user_text)
    if index is None:
        return command
    corrected = {"tool": "play_playlist", "index": index}
    if command != corrected:
        print(f"Playlist validation: corrected LLM call {command} -> {corrected}")
        if request_id:
            log_event(request_id, "playlist_call_corrected", text=user_text, llm_command=command, corrected_command=corrected)
    return corrected

def correct_video_index(user_text: str, command: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    if command.get("tool") != "play_video":
        return command
    explicit = extract_video_index(user_text)
    if explicit is not None and explicit != command["visible_index"]:
        print(f"Index validation: corrected LLM index {command['visible_index']} -> {explicit}")
        if request_id:
            log_event(request_id, "index_corrected", text=user_text, llm_index=command["visible_index"], corrected_index=explicit)
        return {**command, "visible_index": explicit}
    return command

def direct_playback_command(user_text):
    text=re.sub(r"[^a-z0-9 ]", "", user_text.lower())
    text=" ".join(text.split())
    text=re.sub(r"^(please |can you |could you )", "", text)
    text=re.sub(r" please$", "", text)
    if text in {"continue","resume","carry on","keep playing","play","unpause",
                "continue playing","resume playback","continue playback","continue the video",
                "resume the video","continue the current video","resume the current video",
                "continue the same video","play the current video","continue the song","resume the song"}:
        return {"tool":"media_control","action":"play"}
    return None


def guard_command_intent(user_text, command):
    if command.get('tool')=='scroll_page' and not re.search(r"\b(scroll|page)\b",user_text,re.I):
        return {"tool":"resume_current"}
    return command


def request_tool_call(user_text: str, request_id: str | None = None) -> dict[str, Any]:
    """Ask Ollama to convert a user instruction into a tool call."""
    direct=direct_playback_command(user_text)
    if direct is not None:return direct
    payload = {
        "model": CONFIG["model"],
        "stream": False,
        "format": "json",
        "think": False,  # Qwen3 thinking can consume the short generation budget.
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "options": {"temperature": 0, "num_predict": 256},
    }

    response = requests.post(CONFIG["ollama_url"], json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    message = data.get("message", {})
    raw = message.get("content", "")

    if not isinstance(raw, str) or not raw.strip():
        print("Ollama response (diagnostic):", json.dumps(data, indent=2)[:3000])
        raise ValueError("Ollama returned no JSON content. Check model thinking/output settings.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        print("Raw Ollama content:", repr(raw))
        raise ValueError(f"Ollama returned invalid JSON: {error}") from error

    if request_id:
        log_event(request_id, "llm_raw_tool_call", command=parsed)
    # Explicit numbered playlist requests override the model's tool family.
    # Validate the corrected command, rather than rejecting an unrelated but valid LLM call.
    corrected = correct_playlist_selection(user_text, parsed, request_id)
    try:command = validate_tool_call(corrected)
    except ValueError:return {'tool':'resume_current'}
    return guard_command_intent(user_text, correct_video_index(user_text, command, request_id))


def validate_tool_call(value: Any) -> dict[str, Any]:
    """Allow only commands understood by the installed Chrome extension."""
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object, received: {value!r}")

    tool = value.get("tool")

    if tool == "resume_current":
        return {"tool":"resume_current"}

    if tool == "youtube_search":
        query = value.get("query")
        if isinstance(query, str) and query.strip():
            return {"tool": tool, "query": query.strip()}

    elif tool == "scroll_page":
        direction = value.get("direction")
        fraction = value.get("fraction")
        if direction in ("up", "down") and type(fraction) in (int, float) and fraction in (0.5, 1):
            return {"tool": tool, "direction": direction, "fraction": fraction}

    elif tool == "play_video":
        index = value.get("visible_index")
        if type(index) is int and 1 <= index <= 10000:
            return {"tool": tool, "visible_index": index}

    elif tool == "media_control":
        action = value.get("action")
        if action in ("pause", "play", "seek_forward", "seek_backward"):
            return {"tool": tool, "action": action}

    elif tool in ("show_playlists", "open_playlists", "list_playlists"):
        return {"tool": "show_playlists"}

    elif tool == "play_playlist":
        index = value.get("index")
        if type(index) is int and 1 <= index <= 10000:
            return {"tool": tool, "index": index}
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return {"tool": tool, "name": name.strip()}

    elif tool == "playlist_control":
        action = value.get("action")
        if action in ("next", "previous", "shuffle"):
            return {"tool": tool, "action": action}

    elif tool == "set_volume":
        percentage = value.get("percentage")
        if type(percentage) is int and 0 <= percentage <= 100:
            return {"tool": tool, "percentage": percentage}

    raise ValueError(f"Unsupported or invalid tool call: {value!r}")


def start_local_server() -> None:
    """Serve the extension's polling endpoint on localhost only."""
    APP.run(
        host="127.0.0.1",
        port=int(CONFIG.get("port", 8765)),
        debug=False,
        use_reloader=False,
    )


def browser_request(command, timeout=12):
    command = {**command, "request_id": command.get("request_id", str(uuid.uuid4()))}
    rid = command["request_id"]
    COMMANDS.put(command)
    with RESULT_CONDITION:
        arrived = RESULT_CONDITION.wait_for(lambda: rid in RESULTS, timeout=timeout)
        return RESULTS.pop(rid) if arrived else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-debug', action='store_true', help='Skip diagnostic snapshots/screenshots and persistent logs')
    parser.add_argument('--wake', action='store_true', help='Hands-free Hey Sitara test mode')
    parser.add_argument('--voice', action='store_true', help='Stationary push-to-talk testing; hold F8')
    args = parser.parse_args()
    voice = None
    wake = None
    if args.voice or args.wake:
        try:
            from voice_io import VoiceIO
            voice = VoiceIO(CONFIG.get('voice', {}))
            if args.wake:
                from wake_word import WakeInput
                wake = WakeInput(CONFIG.get('voice', {}))
        except Exception as exc:
            print(f'Voice setup failed: {exc}. Use python assistant.py for typed mode.')
            return
    server = threading.Thread(target=start_local_server, daemon=True)
    server.start()

    print("Treadmill Assistant ready.")
    print("Open the extension controller tab via the Chrome toolbar icon.")
    print("Keep the controller tab open; switch back to YouTube to browse.")
    print("Input mode:", "wake phrase" if wake else "F8 push-to-talk" if voice else "typed")
    print("Debug diagnostics:", "on" if DEBUG_MODE else "off")
    print("Press Ctrl+C to exit.\n")

    if voice:
        voice.speak(f'Wake input loaded. Keep the Controller tab open. Say {wake.phrase}, wait for the beep, then speak.' if wake else 'Voice input loaded. Keep the Controller tab open. Hold F8 to speak while stationary.')
    while True:
        rid = str(uuid.uuid4())[:12]
        pause_state = None
        command = None
        announcement = None
        result = None
        def release_wake_pause():
            nonlocal pause_state
            if not pause_state or not pause_state.get('was_playing'):return
            from interaction import should_restore
            try:
                restored = browser_request({"tool":"__wake_release", "token":rid,
                    "tab_id":pause_state.get('tab_id'), "restore":should_restore(command,result)}, timeout=3)
                print('Wake pause cleanup:',json.dumps(restored or {'ok':False,'error':'controller_timeout'}),flush=True)
                if restored and restored.get('ok'):pause_state=None
                else:print('Wake pause cleanup unavailable; check playback.',flush=True)
            except Exception as exc:
                print('Wake pause cleanup failed:',exc,flush=True)
        def pause_for_command():
            nonlocal pause_state
            pause_state = browser_request({"tool":"__wake_pause", "token":rid,
                                           "expires_at":time.time()+3}, timeout=3)
            print('Wake pause result:', json.dumps(pause_state or {'ok':False,'error':'controller_timeout'}), flush=True)
            if not pause_state or not pause_state.get('ok'):
                print('Wake pause unavailable; continuing command capture.', flush=True)
        try:
            if voice:
                user_text, timing = wake.listen(voice, on_wake=pause_for_command) if wake else voice.listen()
                if user_text:
                    print('Heard:', user_text)
                    log_event(rid, 'asr_transcript', text=user_text, **timing)
            else:
                user_text = input("Command> ").strip()
            if not user_text:
                continue
            pipeline_start = time.monotonic()
            stages = dict(timing) if voice else {}
            log_event(rid, "user_input", text=user_text)
            # Capture the user's browser state before the LLM interprets the command.
            stage_start = time.monotonic()
            fast_playback = direct_playback_command(user_text) is not None
            before = {"ok":True,"skipped":True} if fast_playback else browser_snapshot(rid, "before")
            stages["before_snapshot_s"] = round(time.monotonic()-stage_start,3)
            if not before.get("ok"):
                print("Snapshot warning:", before.get("error", "unknown"))
            t0 = time.monotonic()
            command = request_tool_call(user_text, rid)
            log_event(rid, "validated_tool_call", command=command, latency_s=round(time.monotonic()-t0, 3))
            stages["llm_s"] = round(time.monotonic()-t0,3)
            print("Tool call:", json.dumps(command, indent=2))
            stage_start = time.monotonic()
            command["request_id"] = rid
            COMMANDS.put(command)
            if voice:
                from interaction import ConcurrentSpeech
                from voice_io import action_announcement
                announcement = ConcurrentSpeech(voice, action_announcement(command))
            with RESULT_CONDITION:
                arrived = RESULT_CONDITION.wait_for(lambda: rid in RESULTS, timeout=12)
                result = RESULTS.pop(rid) if arrived else None
            stages["browser_action_s"] = round(time.monotonic()-stage_start,3)
            stages["transcript_to_browser_result_s"] = round(time.monotonic()-pipeline_start,3)
            if "wake_to_transcript_s" in stages:
                stages["wake_to_browser_result_s"] = round(stages["wake_to_transcript_s"] + stages["transcript_to_browser_result_s"],3)
            print("Action timing:", json.dumps(stages), flush=True)
            if result is None or not result.get('ok'):
                release_wake_pause()
            if announcement:
                announcement.finish()
                stages["announcement_s"] = announcement.seconds
            stage_start = time.monotonic()
            if voice:
                if result is None:
                    voice.speak('Browser response timed out. Check the Controller connection.')
                elif not result.get('ok'):
                    voice.speak('That action failed. ' + str(result.get('error', 'Unknown error')).replace('_', ' '))
                elif command['tool'] == 'show_playlists':
                    voice.speak(f"Found {len(result.get('playlists', []))} loaded playlists.")
            stages["result_speech_s"] = round(time.monotonic()-stage_start,3)
            stage_start = time.monotonic()
            # Controller waits for smooth scrolling; snapshot retries until the
            # destination content script is ready after navigation.
            if DEBUG_MODE and command["tool"] in ("youtube_search", "play_video", "show_playlists", "play_playlist"):
                time.sleep(0.5)
            after = {"ok":True,"skipped":True} if command["tool"] in ("media_control","resume_current") else browser_snapshot(rid, "after")
            stages["after_snapshot_s"] = round(time.monotonic()-stage_start,3)
            print("Ready timing:", json.dumps(stages), flush=True)
            log_event(rid, "stage_timings", **stages)
            if command["tool"] in ("youtube_search", "play_video", "show_playlists", "play_playlist") and after.get("ok") and not after.get("skipped"):
                state = after.get("state") or {}
                expected_url = (result or {}).get("url") or ((result or {}).get("selected") or {}).get("url")
                actual_url = state.get("url", "")
                if expected_url and actual_url:
                    # Search pages can canonicalize their URL; compare search query
                    # semantically rather than requiring identical URL formatting.
                    from urllib.parse import urlparse, parse_qs
                    e, a = urlparse(expected_url), urlparse(actual_url)
                    matched = (e.path == a.path and
                               (e.path != "/results" or
                                parse_qs(e.query).get("search_query") == parse_qs(a.query).get("search_query")))
                    log_event(rid, "navigation_verified", matched=matched, expected=expected_url, actual=actual_url)
                    if not matched:
                        print("Navigation warning: destination URL differs from selected URL.")
                if command["tool"] == "play_video":
                    player = state.get("player")
                    if player is None:
                        log_event(rid, "playback_verification", status="player_not_found")
                        print("Playback warning: no video player found in post-action snapshot.")
                    else:
                        status = "playing" if not player.get("paused", True) else "paused_or_buffering"
                        log_event(rid, "playback_verification", status=status, player=player)
                        print("Playback status:", status)
            if not after.get("ok"):
                print("Post-action snapshot warning:", after.get("error", "unknown"))
            if result is None:
                print("Browser response timed out. Check that the controller tab is open.")
                log_event(rid, "browser_timeout", timeout_s=12)
            elif result.get("ok"):
                print("Browser:", result.get("detail", "Command accepted"))
                if command["tool"] == "show_playlists":
                    playlists = result.get("playlists", [])
                    for i, item in enumerate(playlists, 1):
                        print(f"  {item.get('index', i)}. {item.get('title', '(untitled)')}")
                    if not playlists:
                        print("No playlists extracted. Check that YouTube is signed in and playlists are loaded.")
                if result.get("selected"):
                    print("Selected:", result["selected"].get("title", ""))
            else:
                print("Browser FAILED:", result.get("error", "unknown error"))
                if result.get("available") is not None:
                    print("Available numbered entries:", json.dumps(result["available"], ensure_ascii=False))
        except (KeyboardInterrupt, EOFError):
            print("\nStopping assistant.")
            break
        except requests.RequestException as error:
            print(f"Ollama connection error: {error}")
            log_event(rid, "llm_error", error=str(error))
            release_wake_pause()
            if voice: voice.speak("I could not process that command. Check the terminal.")
        except (ValueError, KeyError, TypeError) as error:
            print(f"Command error: {error}")
            log_event(rid, "llm_error", error=str(error))
            release_wake_pause()
            if voice: voice.speak("I could not process that command. Check the terminal.")
        except Exception as error:
            if not voice: raise
            print(f'Voice error: {error}')
            log_event(rid, 'voice_error', error=str(error))
            release_wake_pause()
            voice.speak('Voice input failed. Check the terminal.')
            break
        finally:
            if announcement:
                announcement.finish()
            release_wake_pause()


if __name__ == "__main__":
    main()
