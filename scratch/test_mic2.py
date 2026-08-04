import sounddevice as sd
import numpy as np
import time, sys

print("=== TESTING MIC ENERGY DYNAMIC THRESHOLD ===", flush=True)

energies = []
def callback(indata, frames, time_info, status):
    pcm = indata[:, 0].astype(np.float32)
    energy = float(np.sqrt(np.mean(pcm**2)))
    energies.append(energy)
    if energy > 0.00005:
        print(f"Captured audio energy: {energy:.6f} [SPEECH DETECTED!]", flush=True)

try:
    stream = sd.InputStream(samplerate=44100, channels=1, callback=callback)
    stream.start()
    print("Listening for 3 seconds... Speak now if testing mic!", flush=True)
    time.sleep(3.0)
    stream.stop()
    stream.close()
    print(f"Min energy={min(energies):.6f}, Max energy={max(energies):.6f}, Avg={np.mean(energies):.6f}", flush=True)
except Exception as e:
    print(f"Error: {e}", flush=True)
