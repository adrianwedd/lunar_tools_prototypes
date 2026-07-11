#!/usr/bin/env python3
"""On-machine smoke test for EmotionDetector.

Opens the default camera, runs face + emotion detection on live frames,
overlays the primary emotion label + confidence on each detected face, and
reports the achieved FPS.

Requires a fetched ONNX model for real (non-placeholder) results:

    python scripts/fetch_models.py

Run with real hardware attached (not under LUNAR_HEADLESS):

    python scripts/smoke_emotion.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lunar_tools_art.emotion import EmotionDetector  # noqa: E402
from lunar_tools_art.tools.camera import WebCam  # noqa: E402


def main():
    detector = EmotionDetector()
    print(f"has_classifier={detector.has_classifier}")
    if not detector.has_classifier:
        print(
            "No ONNX model loaded — showing placeholder output. "
            "Run scripts/fetch_models.py first for real emotion labels."
        )

    cam = WebCam(cam_id=0)
    import cv2

    print("Showing emotion overlay for 10 seconds (press any key to stop early)...")
    start = time.time()
    frame_count = 0
    while time.time() - start < 10.0:
        frame = cam.get_img()
        if frame is None:
            print("No camera frame available; camera degraded.")
            break
        frame_bgr = frame[..., ::-1]  # RGB -> BGR for OpenCV
        results = detector.detect(frame_bgr)
        for r in results:
            x, y, w, h = r.bbox
            cv2.rectangle(frame_bgr, (x, y), (x + w, y + h), (0, 255, 0), 2)
            label = f"{r.primary_emotion} ({r.confidence:.2f})"
            cv2.putText(
                frame_bgr,
                label,
                (x, max(y - 10, 0)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
        cv2.imshow("smoke_emotion", frame_bgr)
        frame_count += 1
        if cv2.waitKey(1) != -1:
            break

    elapsed = time.time() - start
    fps = frame_count / elapsed if elapsed > 0 else 0.0
    print(f"Frames: {frame_count}, elapsed: {elapsed:.2f}s, FPS: {fps:.2f}")

    cv2.destroyAllWindows()
    cam.release()
    print("Done.")


if __name__ == "__main__":
    main()
