"""Level-gated digital gain; dBFS is a digital level, not acoustic SPL."""
from collections import deque
import math


class SpeechGain:
    def __init__(self, settings=None, vad=None):
        import numpy as np
        self.np=np
        self.settings=settings or {}
        self.enabled=self.settings.get('enabled',True)
        self.target=float(self.settings.get('target_dbfs',-24))
        self.max_gain=10**(float(self.settings.get('max_gain_db',18))/20)
        self.floor=float(self.settings.get('minimum_dbfs',-60))
        self.gain=1.0
        self.history=deque(maxlen=50)  # last 0.5 sec of speech, in 10 ms windows
        self.level_dbfs=None
        self.input_energy=0.0; self.output_energy=0.0; self.active_samples=0
        self.max_applied_gain=1.0; self.limited_blocks=0

    def process_float(self, audio, sample_rate=16000):
        if sample_rate!=16000:raise ValueError('SpeechGain expects 16 kHz mono audio')
        np=self.np;x=np.asarray(audio,dtype='float32').reshape(-1)
        if not self.enabled or not len(x):return x.copy()
        # Estimate level from original samples above the floor; no VAD prerequisite.
        speech=False
        for start in range(0,len(x)-159,160):
            frame=x[start:start+160]
            power=float(np.mean(frame.astype('float64')**2))
            db=10*math.log10(max(power,1e-12))
            if db>=self.floor:
                self.history.append(power);speech=True
        if speech and self.history:
            self.level_dbfs=10*math.log10(max(sum(self.history)/len(self.history),1e-12))
            desired=min(self.max_gain,max(1.0,10**((self.target-self.level_dbfs)/20)))
        else:
            # Below the floor, smoothly return to unity.
            desired=1.0
        duration=len(x)/16000
        tau=0.15 if desired>self.gain else 0.35
        next_gain=self.gain+(desired-self.gain)*(1-math.exp(-duration/tau))
        gains=np.linspace(self.gain,next_gain,len(x),dtype='float32')
        y=x*gains
        peak=float(np.max(np.abs(y)))
        limiter=min(1.0,0.95/max(peak,1e-12))
        y*=limiter
        if limiter<1.0:self.limited_blocks+=1
        self.max_applied_gain=max(self.max_applied_gain,float(np.max(gains))*limiter)
        for start in range(0,len(x)-159,160):
            frame=x[start:start+160].astype("float64")
            power=float(np.mean(frame**2))
            if 10*math.log10(max(power,1e-12))>=self.floor:
                self.input_energy+=float(np.sum(frame**2))
                self.output_energy+=float(np.sum(y[start:start+160].astype("float64")**2))
                self.active_samples+=160
        self.gain=next_gain
        return y.astype('float32')

    def process_pcm(self, audio):
        y=self.process_float(self.np.asarray(audio,dtype='float32')/32768)
        return self.np.clip(self.np.rint(y*32768),-32768,32767).astype('int16')

    def diagnostics(self):
        """Levels of above-floor audio, including any noise; actual post-limiter gain."""
        def db(power):return round(10*math.log10(max(power,1e-12)),2)
        n=self.active_samples
        return {"input_active_dbfs":db(self.input_energy/n) if n else None,
                "output_active_dbfs":db(self.output_energy/n) if n else None,
                "effective_gain_db":db(self.output_energy/self.input_energy) if self.input_energy else None,
                "max_applied_gain_db":round(20*math.log10(max(self.max_applied_gain,1e-12)),2),
                "above_floor_seconds":round(n/16000,3),"limited_blocks":self.limited_blocks}
