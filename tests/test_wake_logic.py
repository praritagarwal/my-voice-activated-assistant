import unittest
from unittest.mock import Mock
from wake_word import CommandBoundary, WakeInput


class BoundaryTests(unittest.TestCase):
    def run_frames(self, boundary, flags):
        for voiced in flags:
            outcome = boundary.step(voiced)
            if outcome: return outcome
        return None

    def test_initial_silence_cancels(self):
        self.assertEqual(self.run_frames(CommandBoundary(), [False]*170), 'no_speech')

    def test_short_noise_is_not_a_command(self):
        self.assertEqual(self.run_frames(CommandBoundary(), [True]*3+[False]*31), 'no_speech')

    def test_speech_then_silence_completes(self):
        self.assertEqual(self.run_frames(CommandBoundary(), [False]*10+[True]*20+[False]*31), 'complete')

    def test_brief_pause_does_not_end_command(self):
        self.assertIsNone(self.run_frames(CommandBoundary(), [True]*20+[False]*10+[True]*20))

    def test_max_duration_discards(self):
        self.assertEqual(self.run_frames(CommandBoundary(maximum=1), [True]*40), 'too_long')

    def test_empty_capture_never_calls_asr(self):
        wake = WakeInput.__new__(WakeInput)
        wake.wait=Mock();wake.cue=Mock();wake.capture=Mock(return_value=(None,{'cancelled':True}))
        voice=Mock()
        text,timing=wake.listen(voice)
        self.assertEqual(text,'');voice.asr.transcribe.assert_not_called()
        wake.wait.assert_called_once();wake.cue.assert_called_once()

    def test_command_transcription_excludes_detector_output(self):
        wake=WakeInput.__new__(WakeInput);wake.phrase='Hey Sitara'
        wake.wait=Mock(return_value='HEY SITARA');wake.cue=Mock();wake.capture=Mock(return_value=([0.1],{'audio_seconds':1}))
        voice=Mock();segment=Mock();segment.text=' pause the video '
        voice.asr.transcribe.return_value=(iter([segment]),None)
        text,timing=wake.listen(voice)
        self.assertEqual(text,'pause the video');self.assertEqual(timing['wake_phrase'],'Hey Sitara')


if __name__=='__main__':unittest.main()
