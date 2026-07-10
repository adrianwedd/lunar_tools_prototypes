#!/usr/bin/env python3
"""On-machine smoke test for WebCam.

Opens the default camera and displays live frames via cv2.imshow for 5
seconds.

Run with real hardware attached (not under LUNAR_HEADLESS):

    python scripts/smoke_camera.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lunar_tools_art.tools.camera import WebCam  # noqa: E402


def main():
    cam = WebCam(cam_id=0)
    import cv2

    print(
        "Showing camera feed for 5 seconds (press any key in the window to stop early)..."
    )
    start = time.time()
    while time.time() - start < 5.0:
        frame = cam.get_img()
        if frame is None:
            print("No camera frame available; camera degraded.")
            break
        cv2.imshow("smoke_camera", frame[..., ::-1])  # back to BGR for display
        if cv2.waitKey(1) != -1:
            break

    cv2.destroyAllWindows()
    cam.release()
    print("Done.")


if __name__ == "__main__":
    main()
