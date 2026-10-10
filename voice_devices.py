"""List PortAudio input/output devices for config.json."""
import sounddevice as sd
print(sd.query_devices())
print('Default input/output:', sd.default.device)
print('Set voice.input_device/output_device to an integer ID if defaults are wrong.')
