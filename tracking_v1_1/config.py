from __future__ import annotations

AUTO_FOLLOW_POLICY = "FIRST_ACTIVE"

AUTO_FOLLOW_POLICIES = (
    "FIRST_ACTIVE",
    "HIGHEST_CONFIDENCE",
    "LARGEST_BBOX",
    # "NEAREST_CENTER",
)

# Dev2 operational mode: accept only local model class 0 (drone).
TRACKING_DRONE_ONLY = True

# Minimum detection confidence used when drone-only mode is enabled.
TRACKING_DRONE_CONF = 0.15

# Inference image size passed to Ultralytics when drone-only mode is enabled.
TRACKING_IMGSZ = 960

# Positive observations required before a tentative track is emitted.
TRACKING_MIN_CONFIRM_HITS = 2

# Rolling processed-frame window in which those hits must occur.
TRACKING_CONFIRM_WINDOW = 4

# Ultralytics tracker backend used by Dev2TrackingProvider.
# ByteTrack assigns persistent IDs more reliably than TrackTrack
# on the current far-range drone clips.
TRACKING_TRACKER = "bytetrack.yaml"

# Same-frame IoU threshold for treating two drone boxes as one target.
TRACKING_DUPLICATE_IOU = 0.60