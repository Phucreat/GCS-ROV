import sounddevice as sd
import numpy as np
import time, sys

print("=== SOUNDDEVICE MICROPHONE DIAGNOSTIC TEST ===", flush=True)
devices = sd.query_devices()
input_devices = []
for idx, dev in enumerate(devices):
    if dev['max_input_channels'] > 0:
        input_devices.append((idx, dev['name'], dev['default_samplerate']))
        print(f"Device [{idx}]: {dev['name']} (Channels: {dev['max_input_channels']}, Default SR: {dev['default_samplerate']} Hz)", flush=True)

print(f"\nDefault Input Device Index: {sd.default.device[0]}", flush=True)

def test_device(dev_idx, name, sr):
    print(f"\n--- Testing Device [{dev_idx}] {name} at {sr} Hz... ---", flush=True)
    energies = []
    def callback(indata, frames, time_info, status):
        energy = float(np.sqrt(np.mean(indata[:, 0]**2)))
        energies.append(energy)

    try:
        stream = sd.InputStream(device=dev_idx, samplerate=sr, channels=1, callback=callback)
        stream.start()
        time.sleep(1.0)
        stream.stop()
        stream.close()
        max_e = max(energies) if energies else 0.0
        avg_e = np.mean(energies) if energies else 0.0
        print(f"Result [{dev_idx}]: Chunks={len(energies)}, Max Energy={max_e:.6f}, Avg={avg_e:.6f}", flush=True)
        return max_e
    except Exception as e:
        print(f"Error [{dev_idx}]: {e}", flush=True)
        return 0.0

# Test first 5 input devices
for idx, name, sr in input_devices[:6]:
    test_device(idx, name, int(sr))
