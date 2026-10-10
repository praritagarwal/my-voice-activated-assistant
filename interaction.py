"""Speech concurrency and temporary playback policy."""
import threading
import time


def should_restore(command):
    if command is None:return True
    tool=command.get('tool')
    if tool in ('resume_current','play_video','play_playlist','youtube_search','show_playlists','open_playlists'):return False
    if tool=='media_control' and command.get('action') in ('pause','play'):return False
    if tool=='playlist_control' and command.get('action') in ('next','previous'):return False
    return True


class ConcurrentSpeech:
    def __init__(self, voice, text):
        self.seconds=0.0
        def speak():
            start=time.monotonic()
            try:voice.speak(text)
            except Exception as exc:print('Announcement failed:',exc,flush=True)
            finally:self.seconds=round(time.monotonic()-start,3)
        self.thread=threading.Thread(target=speak,daemon=True)
        self.thread.start()
    def finish(self):self.thread.join()
