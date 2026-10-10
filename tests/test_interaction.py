import threading
import unittest
from interaction import ConcurrentSpeech, should_restore

class InteractionTests(unittest.TestCase):
    def test_playback_intent_prevents_resume(self):
        for tool,action in [('media_control','pause'),('media_control','play'),('playlist_control','next'),('playlist_control','previous'),('play_video',None),('play_playlist',None),('youtube_search',None),('show_playlists',None)]:
            self.assertFalse(should_restore({'tool':tool,'action':action}))
    def test_non_playback_and_cancel_resume(self):
        for command in [None,{'tool':'set_volume'},{'tool':'scroll_page'},{'tool':'media_control','action':'seek_forward'},{'tool':'playlist_control','action':'shuffle'}]:
            self.assertTrue(should_restore(command))
    def test_announcement_does_not_block_action(self):
        entered=threading.Event();release=threading.Event()
        class Voice:
            def speak(self,text):entered.set();release.wait(2)
        speech=ConcurrentSpeech(Voice(),'Playing')
        self.assertTrue(entered.wait(1))
        self.assertTrue(speech.thread.is_alive())
        release.set();speech.finish()
        self.assertFalse(speech.thread.is_alive())
