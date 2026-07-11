#!/usr/bin/env python3
"""On-machine smoke test for MidiInput.

Opens the first available MIDI input device and prints incoming messages
for 5 seconds.

Run with a real MIDI device attached (not under LUNAR_HEADLESS):

    python scripts/smoke_midi.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lunar_tools_art.tools.input import MidiInput  # noqa: E402


def main():
    midi = MidiInput()

    print("Listening for MIDI messages for 5 seconds...")
    start = time.time()
    while time.time() - start < 5.0:
        msg = midi.get_latest_message()
        if msg is not None:
            print(msg)
        time.sleep(0.05)

    midi.close()
    print("Done.")


if __name__ == "__main__":
    main()
