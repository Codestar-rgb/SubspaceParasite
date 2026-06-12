#!/usr/bin/env python3
"""
Super Converter — Configuration
=================================
Central configuration constants for the Super Architecture converter.
"""

# ============================================================================
# Pipeline Configuration
# ============================================================================

# Carry-forward: minimum time gap (seconds) to consider a keyframe as "missing"
CARRY_FORWARD_MIN_GAP = 0.01

# Period analysis: minimum number of keyframes to attempt period detection
PERIOD_MIN_KEYFRAMES = 4

# Loop alignment: maximum allowed mismatch between first/last keyframe values
LOOP_ALIGN_TOLERANCE = 0.01  # degrees for rotation, units for position

# Rotation normalization: target range
ROTATION_NORMALIZE_MIN = -360.0
ROTATION_NORMALIZE_MAX = 360.0

# Snap detection: threshold for considering a keyframe transition a "snap"
SNAP_THRESHOLD_DEGREES = 30.0  # degrees

# Snap detection: fraction of snaps to consider a channel "snap-heavy"
SNAP_HEAVY_FRACTION = 0.5

# Keyframe rounding precision for bbmodel output
BBMODEL_DECIMAL_PLACES = 6

# UUID length (hex characters) — 16 for low collision risk
UUID_LENGTH = 16

# ============================================================================
# Model Conversion Configuration
# ============================================================================

# Default texture dimensions when not specified in source
DEFAULT_TEXTURE_WIDTH = 64
DEFAULT_TEXTURE_HEIGHT = 32

# Default entity height for Y offset calculation
DEFAULT_ENTITY_HEIGHT = 24.0

# Y offset tolerance — don't shift if model is within this distance of Y=0
Y_OFFSET_TOLERANCE = 0.5

# ============================================================================
# Batch Processing Configuration
# ============================================================================

# Garbage collection interval (number of models between GC calls)
GC_INTERVAL = 20

# Maximum number of errors to display in summary
MAX_ERRORS_DISPLAY = 10

# ============================================================================
# Face Names (in .bbmodel order)
# ============================================================================

FACE_NAMES = ["north", "east", "south", "west", "up", "down"]
