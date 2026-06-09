"""AnimForge v19 Main Orchestrator

Coordinates the full conversion pipeline:
1. Parse .bbmodel
2. Profile all animations
3. Deduplicate
4. Differentiate identical cross-category animations
5. Route to pipelines
6. Quality gate
7. Serialize to GeckoLib
8. Write output

Also includes batch_convert() and CLI entry point.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .core.config import AnimForgeConfig
from .core.parser import BBModelParser, ParsedAnimation
from .core.profiler import AnimationProfiler
from .core.profile import AnimationProfile, AnimCategory
from .pipelines.router import PipelineRouter
from .stages.dedup import DedupEngine, DedupResult
from .stages.differentiator import AnimationDifferentiator
from .quality.gate import QualityGate, GateResult
from .quality.report import QualityReporter, QualityReport
from .output.geckolib import GeckoLibSerializer

logger = logging.getLogger("animforge")


@dataclass
class ConversionResult:
    """Result of a single animation conversion.

    Attributes:
        name: Animation name.
        profile: Animation profile.
        gate_result: Quality gate result (if checked).
        success: Whether conversion succeeded.
        error: Error message if conversion failed.
    """
    name: str = ""
    profile: Optional[AnimationProfile] = None
    gate_result: Optional[GateResult] = None
    success: bool = True
    error: str = ""


@dataclass
class BatchResult:
    """Result of a batch conversion.

    Attributes:
        results: Per-animation conversion results.
        output_path: Path to the output file.
        total_animations: Total number of animations processed.
        successful: Number of successful conversions.
        failed: Number of failed conversions.
    """
    results: List[ConversionResult] = field(default_factory=list)
    output_path: str = ""
    total_animations: int = 0
    successful: int = 0
    failed: int = 0


class AnimForgeConverter:
    """Main orchestrator for the AnimForge v19 animation conversion pipeline.

    Usage:
        converter = AnimForgeConverter()
        result = converter.convert("model.bbmodel", "model.animation.json")
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()
        self.parser = BBModelParser(self.config)
        self.profiler = AnimationProfiler(self.config)
        self.dedup = DedupEngine()
        self.differentiator = AnimationDifferentiator(self.config)
        self.router = PipelineRouter(self.config)
        self.quality_gate = QualityGate(self.config)
        self.serializer = GeckoLibSerializer(self.config)

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
        model_name: str = "",
        skip_quality_gate: bool = False,
    ) -> BatchResult:
        """Convert a .bbmodel file to GeckoLib .animation.json format.

        Args:
            input_path: Path to the .bbmodel file.
            output_path: Path for the output .animation.json file.
                         Defaults to same directory as input with .animation.json extension.
            model_name: Override model name for animation identifiers.
            skip_quality_gate: Whether to skip quality gate validation.

        Returns:
            BatchResult with conversion details.
        """
        input_path = Path(input_path)

        if output_path is None:
            output_path = input_path.with_suffix(".animation.json")
        else:
            output_path = Path(output_path)

        # Resolve model name
        if not model_name and self.config.model_name:
            model_name = self.config.model_name

        result = BatchResult(output_path=str(output_path))

        try:
            # Step 1: Parse .bbmodel
            logger.info("Parsing %s", input_path)
            parsed_animations = self.parser.parse_file(input_path)
            if not parsed_animations:
                logger.warning("No animations found in %s", input_path)
                return result

            logger.info("Found %d animations", len(parsed_animations))

            # Step 2: Profile all animations
            logger.info("Profiling animations")
            profiles = []
            for anim in parsed_animations:
                profile = self.profiler.profile(anim)
                profiles.append(profile)
                logger.info(
                    "  %s → category=%s, bones=%d, KFs=%d, loop=%s",
                    anim.name, profile.category.value, profile.bone_count,
                    profile.total_keyframes, profile.loop,
                )

            # Step 3: Deduplicate
            logger.info("Deduplicating")
            anim_profile_pairs = list(zip(parsed_animations, profiles))
            dedup_result = self.dedup.deduplicate(anim_profile_pairs)

            if dedup_result.aliases:
                logger.info("  Merged %d same-category duplicates", len(dedup_result.aliases))
            if dedup_result.needs_differentiation:
                logger.info(
                    "  %d animations need differentiation: %s",
                    len(dedup_result.needs_differentiation),
                    dedup_result.needs_differentiation,
                )

            # Step 4: Differentiate identical cross-category animations
            kept_animations: List[ParsedAnimation] = []
            kept_profiles: List[AnimationProfile] = []

            for anim, profile in dedup_result.kept:
                if anim.name in dedup_result.needs_differentiation:
                    # Apply differentiation BEFORE pipeline processing
                    logger.info("  Differentiating %s (category=%s)", anim.name, profile.category.value)
                    anim = self.differentiator.differentiate(anim, profile)

                kept_animations.append(anim)
                kept_profiles.append(profile)

            # Step 5: Route to pipelines and process
            logger.info("Processing animations through pipelines")
            processed_animations: List[ParsedAnimation] = []
            conversion_results: List[ConversionResult] = []

            for anim, profile in zip(kept_animations, kept_profiles):
                conv_result = ConversionResult(name=anim.name, profile=profile)

                try:
                    original = anim.deep_copy()  # Keep for quality gate comparison
                    processed = self.router.route(anim, profile)
                    processed_animations.append(processed)

                    # Step 6: Quality gate
                    if not skip_quality_gate:
                        gate_result = self.quality_gate.validate(original, processed, profile)
                        conv_result.gate_result = gate_result

                        if not gate_result.passed:
                            logger.warning(
                                "  Quality gate FAILED for %s: %s",
                                anim.name,
                                [f[1] for f in gate_result.failures],
                            )
                            # Still include the animation but log the failure
                        else:
                            logger.info("  Quality gate PASSED for %s (health=%.2f)", anim.name, gate_result.report.overall_health if gate_result.report else 1.0)

                    conv_result.success = True
                except Exception as e:
                    logger.error("  Error processing %s: %s", anim.name, e)
                    conv_result.success = False
                    conv_result.error = str(e)
                    # Include the unprocessed animation
                    processed_animations.append(anim)

                conversion_results.append(conv_result)

            # Step 7 & 8: Serialize and write output
            logger.info("Serializing to GeckoLib format")
            self.serializer.write(
                processed_animations,
                kept_profiles,
                output_path,
                model_name=model_name,
            )

            # Update batch result
            result.results = conversion_results
            result.total_animations = len(parsed_animations)
            result.successful = sum(1 for r in conversion_results if r.success)
            result.failed = sum(1 for r in conversion_results if not r.success)

            logger.info(
                "Conversion complete: %d/%d successful → %s",
                result.successful, result.total_animations, output_path,
            )

        except Exception as e:
            logger.error("Conversion failed: %s", e)
            result.failed = 1
            result.total_animations = 1

        return result

    def convert_data(
        self,
        data: Dict[str, Any],
        model_name: str = "",
        skip_quality_gate: bool = False,
    ) -> Tuple[Dict[str, Any], List[ConversionResult]]:
        """Convert .bbmodel data (dict) to GeckoLib format data (dict).

        Useful for programmatic usage without file I/O.

        Args:
            data: Parsed .bbmodel JSON data.
            model_name: Override model name.
            skip_quality_gate: Whether to skip quality gate.

        Returns:
            Tuple of (GeckoLib format dict, conversion results).
        """
        # Step 1: Parse
        parsed_animations = self.parser.parse_data(data)
        if not parsed_animations:
            return {"format_version": "1.8.0", "animations": {}}, []

        # Step 2: Profile
        profiles = [self.profiler.profile(anim) for anim in parsed_animations]

        # Step 3: Deduplicate
        anim_profile_pairs = list(zip(parsed_animations, profiles))
        dedup_result = self.dedup.deduplicate(anim_profile_pairs)

        # Step 4: Differentiate
        kept_animations: List[ParsedAnimation] = []
        kept_profiles: List[AnimationProfile] = []

        for anim, profile in dedup_result.kept:
            if anim.name in dedup_result.needs_differentiation:
                anim = self.differentiator.differentiate(anim, profile)
            kept_animations.append(anim)
            kept_profiles.append(profile)

        # Step 5: Process through pipelines
        processed_animations: List[ParsedAnimation] = []
        conversion_results: List[ConversionResult] = []

        for anim, profile in zip(kept_animations, kept_profiles):
            conv_result = ConversionResult(name=anim.name, profile=profile)
            try:
                original = anim.deep_copy()
                processed = self.router.route(anim, profile)
                processed_animations.append(processed)

                if not skip_quality_gate:
                    conv_result.gate_result = self.quality_gate.validate(original, processed, profile)

                conv_result.success = True
            except Exception as e:
                conv_result.success = False
                conv_result.error = str(e)
                processed_animations.append(anim)

            conversion_results.append(conv_result)

        # Step 7: Serialize
        output = self.serializer.serialize(
            processed_animations, kept_profiles, model_name=model_name
        )

        return output, conversion_results


def batch_convert(
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    model_name: str = "",
    config: AnimForgeConfig | None = None,
) -> List[BatchResult]:
    """Convert all .bbmodel files in a directory.

    Args:
        input_dir: Directory containing .bbmodel files.
        output_dir: Directory for output files. Defaults to input_dir.
        model_name: Override model name.
        config: Configuration. Uses defaults if None.

    Returns:
        List of BatchResult for each converted file.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir) if output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    converter = AnimForgeConverter(config)
    results: List[BatchResult] = []

    bbmodel_files = sorted(input_dir.glob("*.bbmodel"))
    if not bbmodel_files:
        logger.warning("No .bbmodel files found in %s", input_dir)
        return results

    for bbmodel_path in bbmodel_files:
        output_path = output_dir / bbmodel_path.with_suffix(".animation.json").name
        result = converter.convert(bbmodel_path, output_path, model_name=model_name)
        results.append(result)

    return results


def main() -> None:
    """CLI entry point for AnimForge v19."""
    parser = argparse.ArgumentParser(
        description="AnimForge v19 - Blockbench to GeckoLib Animation Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  animforge model.bbmodel
  animforge model.bbmodel -o output.animation.json
  animforge model.bbmodel --model-name ferHuman
  animforge --batch ./models/ --output-dir ./animations/
        """,
    )

    parser.add_argument(
        "input",
        nargs="?",
        help="Input .bbmodel file path",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output .animation.json file path",
    )
    parser.add_argument(
        "--model-name",
        default="",
        help="Override model name in animation identifiers",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch convert all .bbmodel files in input directory",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for batch conversion",
    )
    parser.add_argument(
        "--skip-quality-gate",
        action="store_true",
        help="Skip quality gate validation",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--dp-epsilon",
        type=float,
        help="Override Douglas-Peucker simplification epsilon",
    )
    parser.add_argument(
        "--min-walk-leg-kf",
        type=int,
        help="Override minimum keyframes for walk leg bones",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build config
    config = AnimForgeConfig()
    if args.model_name:
        config.model_name = args.model_name
    if args.dp_epsilon is not None:
        config.dp_epsilon = args.dp_epsilon
    if args.min_walk_leg_kf is not None:
        config.min_kf_walk_leg = args.min_walk_leg_kf

    if args.batch:
        if not args.input:
            parser.error("Input directory required for batch mode")
        results = batch_convert(
            args.input,
            args.output_dir,
            model_name=args.model_name,
            config=config,
        )
        total = sum(r.total_animations for r in results)
        successful = sum(r.successful for r in results)
        failed = sum(r.failed for r in results)
        print(f"\nBatch conversion complete: {successful}/{total} successful, {failed} failed")
        sys.exit(0 if failed == 0 else 1)

    if not args.input:
        parser.error("Input file required (use --batch for directory mode)")

    converter = AnimForgeConverter(config)
    result = converter.convert(
        args.input,
        args.output,
        model_name=args.model_name,
        skip_quality_gate=args.skip_quality_gate,
    )

    print(f"\nConversion complete: {result.successful}/{result.total_animations} successful")

    for conv_result in result.results:
        status = "✓" if conv_result.success else "✗"
        print(f"  {status} {conv_result.name}")
        if conv_result.gate_result and conv_result.gate_result.report:
            health = conv_result.gate_result.report.overall_health
            print(f"    Health: {health:.2f}")

    sys.exit(0 if result.failed == 0 else 1)


if __name__ == "__main__":
    main()
