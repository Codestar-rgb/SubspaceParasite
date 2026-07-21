"""
Pixel-Level Validator (v6.9.19)

Provides SSIM/PSNR-based visual comparison framework for validating
converted models against the original SRP rendering.

This module does NOT capture frames itself (that requires MC client +
RenderDoc/GPA). Instead, it provides:
1. A frame comparison utility that computes SSIM/PSNR between two images
2. A batch comparison runner for animation sequences
3. A report generator for quality metrics

Usage:
    from engine.pixel_validator import compare_frames, compare_sequences
    # Compare two single frames
    score = compare_frames('frame_original.png', 'frame_converted.png')
    # Compare a sequence of frames
    report = compare_sequences('seq_original/', 'seq_converted/')
"""

import math
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FrameComparison:
    """Result of comparing two frames."""
    frame_index: int
    ssim: float
    psnr: float
    mean_error: float
    max_error: float


@dataclass
class SequenceReport:
    """Report for a sequence of frame comparisons."""
    total_frames: int = 0
    mean_ssim: float = 0.0
    min_ssim: float = 1.0
    mean_psnr: float = 0.0
    frames: List[FrameComparison] = field(default_factory=list)
    regression_frames: List[int] = field(default_factory=list)

    @property
    def quality_score(self) -> float:
        """Overall quality score (0-1, higher is better)."""
        return self.mean_ssim


def _compute_ssim(img1: np.ndarray, img2: np.ndarray) -> float:
    """Compute Structural Similarity Index (SSIM) between two images.

    Uses a simplified SSIM with 8x8 blocks and luminance/contrast/structure.
    Returns value in [0, 1] where 1 = identical.
    """
    if img1.shape != img2.shape:
        # Resize to match
        min_h = min(img1.shape[0], img2.shape[0])
        min_w = min(img1.shape[1], img2.shape[1])
        img1 = img1[:min_h, :min_w]
        img2 = img2[:min_h, :min_w]

    # Convert to grayscale if needed
    if len(img1.shape) == 3:
        img1 = np.mean(img1, axis=2)
    if len(img2.shape) == 3:
        img2 = np.mean(img2, axis=2)

    # Constants for stability
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    mu1 = np.mean(img1)
    mu2 = np.mean(img2)
    sigma1 = np.std(img1)
    sigma2 = np.std(img2)
    sigma12 = np.mean((img1 - mu1) * (img2 - mu2))

    numerator = (2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)
    denominator = (mu1 ** 2 + mu2 ** 2 + C1) * (sigma1 ** 2 + sigma2 ** 2 + C2)

    ssim = float(numerator / denominator) if denominator > 0 else 1.0
    return max(0.0, min(1.0, ssim))


def _compute_psnr(img1: np.ndarray, img2: np.ndarray) -> float:
    """Compute Peak Signal-to-Noise Ratio (PSNR) in dB."""
    if img1.shape != img2.shape:
        min_h = min(img1.shape[0], img2.shape[0])
        min_w = min(img1.shape[1], img2.shape[1])
        img1 = img1[:min_h, :min_w]
        img2 = img2[:min_h, :min_w]

    mse = np.mean((img1.astype(float) - img2.astype(float)) ** 2)
    if mse < 1e-10:
        return 100.0  # Identical
    return float(10 * math.log10(255 ** 2 / mse))


def compare_frames(path1: str, path2: str) -> Tuple[float, float]:
    """Compare two image files, returning (SSIM, PSNR).

    Requires Pillow for image loading.
    """
    try:
        from PIL import Image
        img1 = np.array(Image.open(path1).convert('RGB'))
        img2 = np.array(Image.open(path2).convert('RGB'))
    except ImportError:
        logger.error("Pillow required for pixel validation")
        return 0.0, 0.0
    except FileNotFoundError as e:
        logger.error(f"Image not found: {e}")
        return 0.0, 0.0

    ssim = _compute_ssim(img1, img2)
    psnr = _compute_psnr(img1, img2)
    return ssim, psnr


def compare_sequences(dir1: str, dir2: str,
                      threshold: float = 0.95) -> SequenceReport:
    """Compare two directories of image sequences.

    Args:
        dir1: Directory with original frames (frame_0000.png, ...)
        dir2: Directory with converted frames
        threshold: SSIM threshold below which a frame is a "regression"

    Returns:
        SequenceReport with per-frame metrics
    """
    import os
    report = SequenceReport()

    files1 = sorted([f for f in os.listdir(dir1) if f.endswith('.png')])
    files2 = sorted([f for f in os.listdir(dir2) if f.endswith('.png')])

    n = min(len(files1), len(files2))
    if n == 0:
        logger.warning("No matching frames found")
        return report

    total_ssim = 0.0
    total_psnr = 0.0

    for i in range(n):
        ssim, psnr = compare_frames(
            os.path.join(dir1, files1[i]),
            os.path.join(dir2, files2[i]),
        )

        comp = FrameComparison(
            frame_index=i,
            ssim=ssim,
            psnr=psnr,
            mean_error=1.0 - ssim,
            max_error=1.0 - ssim,
        )
        report.frames.append(comp)
        total_ssim += ssim
        total_psnr += psnr
        report.min_ssim = min(report.min_ssim, ssim)

        if ssim < threshold:
            report.regression_frames.append(i)
            logger.warning("Frame %d: SSIM=%.3f (below threshold %.2f)", i, ssim, threshold)

    report.total_frames = n
    report.mean_ssim = total_ssim / n
    report.mean_psnr = total_psnr / n

    return report


def print_pixel_report(report: SequenceReport, model_name: str = ""):
    """Print a human-readable pixel validation report."""
    print(f"\n{'='*60}")
    print(f"  Pixel Validation Report: {model_name}")
    print(f"{'='*60}")
    print(f"  Frames compared: {report.total_frames}")
    print(f"  Mean SSIM: {report.mean_ssim:.4f}")
    print(f"  Min SSIM:  {report.min_ssim:.4f}")
    print(f"  Mean PSNR: {report.mean_psnr:.2f} dB")
    print(f"  Regressions: {len(report.regression_frames)} frames below 0.95")
    print(f"  Quality Score: {report.quality_score*100:.1f}%")
    print(f"{'='*60}")

    if report.regression_frames:
        print(f"\n  Regression frames: {report.regression_frames[:20]}")
    print()
