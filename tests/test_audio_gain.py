import unittest
import numpy as np
from audio_gain import SpeechGain

class FakeVad:
    def __init__(self,speech): self.speech=speech
    def is_speech(self,*args):return self.speech

class GainTests(unittest.TestCase):
    def test_quiet_speech_boosted_and_bounded(self):
        g=SpeechGain(vad=FakeVad(True));x=np.sin(np.arange(1280)*0.1).astype('float32')*0.01
        for _ in range(20):y=g.process_float(x)
        self.assertGreater(np.sqrt(np.mean(y*y)),np.sqrt(np.mean(x*x))*3)
        self.assertLessEqual(g.gain,10**(18/20))
    def test_silence_not_boosted(self):
        g=SpeechGain(vad=FakeVad(False));y=g.process_float(np.zeros(1280))
        self.assertEqual(g.gain,1);self.assertTrue(np.all(y==0))
    def test_below_floor_not_boosted(self):
        g=SpeechGain(vad=FakeVad(False));x=np.ones(1280,dtype='float32')*0.0001
        np.testing.assert_allclose(g.process_float(x),x)
    def test_quiet_audio_boosted_without_speech_gate(self):
        g=SpeechGain(vad=FakeVad(False));x=np.ones(1280,dtype='float32')*0.003
        for _ in range(20):y=g.process_float(x)
        self.assertGreater(float(y.mean()),0.015)
        d=g.diagnostics()
        self.assertGreater(d['effective_gain_db'],10)
        self.assertAlmostEqual(d['output_active_dbfs']-d['input_active_dbfs'],d['effective_gain_db'],places=1)
    def test_metrics_report_limiter_reduction(self):
        g=SpeechGain();g.gain=8;g.process_float(np.ones(1280,dtype='float32')*0.7)
        d=g.diagnostics()
        self.assertEqual(d['limited_blocks'],1)
        self.assertLess(d['effective_gain_db'],3)
    def test_peak_limiter(self):
        g=SpeechGain(vad=FakeVad(True));g.gain=8
        y=g.process_float(np.ones(1280,dtype='float32')*0.7)
        self.assertLessEqual(float(np.max(abs(y))),0.950001)
    def test_pcm_no_integer_overflow(self):
        g=SpeechGain(vad=FakeVad(True));g.gain=8
        y=g.process_pcm(np.array([30000,-30000]*640,dtype=np.int16))
        self.assertGreater(y[0],0);self.assertLess(y[1],0)
    def test_disabled_exact_pcm(self):
        g=SpeechGain({'enabled':False});x=np.array([-32768,-3,0,17,32767],dtype=np.int16)
        np.testing.assert_array_equal(g.process_pcm(x),x)

if __name__=='__main__':unittest.main()
