"""Deduplication Engine

Groups animations by content hash and handles duplicates:
- Identical animations in DIFFERENT categories: keep all, mark for differentiation
- Identical animations in the SAME category: merge (keep one, alias the rest)
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional, Set, Tuple

from ..core.parser import ParsedAnimation
from ..core.profile import AnimationProfile, AnimCategory


class DedupResult:
    """Result of deduplication processing.

    Attributes:
        kept: Animations that survived deduplication (unique originals).
        aliases: Map from alias name → original name (for merged same-category dups).
        needs_differentiation: Set of animation names that need differentiation
                               (cross-category duplicates).
        dedup_groups: Groups of duplicate animations keyed by content hash.
    """

    def __init__(self) -> None:
        self.kept: List[Tuple[ParsedAnimation, AnimationProfile]] = []
        self.aliases: Dict[str, str] = {}
        self.needs_differentiation: Set[str] = set()
        self.dedup_groups: Dict[str, List[Tuple[ParsedAnimation, AnimationProfile]]] = {}


class DedupEngine:
    """Engine for detecting and handling duplicate animations.

    Uses content hashes from AnimationProfile to identify duplicates.
    Duplicates are handled differently based on whether they share
    the same category or not.
    """

    def __init__(self) -> None:
        pass

    def deduplicate(
        self,
        animations: List[Tuple[ParsedAnimation, AnimationProfile]],
    ) -> DedupResult:
        """Deduplicate a list of animations.

        Args:
            animations: List of (ParsedAnimation, AnimationProfile) pairs.

        Returns:
            DedupResult with kept animations, aliases, and differentiation flags.
        """
        result = DedupResult()

        # Group by content hash
        hash_groups: Dict[str, List[Tuple[ParsedAnimation, AnimationProfile]]] = {}
        for anim, profile in animations:
            h = profile.content_hash
            if h not in hash_groups:
                hash_groups[h] = []
            hash_groups[h].append((anim, profile))

        result.dedup_groups = hash_groups

        for content_hash, group in hash_groups.items():
            if len(group) == 1:
                # No duplicates for this hash
                result.kept.append(group[0])
                continue

            # Multiple animations share the same content hash
            # Check if they're in the same or different categories
            categories: Dict[AnimCategory, List[Tuple[ParsedAnimation, AnimationProfile]]] = {}
            for anim, profile in group:
                cat = profile.category
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((anim, profile))

            if len(categories) == 1:
                # All in the same category: merge (keep first, alias the rest)
                cat = list(categories.keys())[0]
                items = categories[cat]
                result.kept.append(items[0])
                for anim, profile in items[1:]:
                    result.aliases[anim.name] = items[0][0].name
            else:
                # Cross-category duplicates: keep all but mark for differentiation
                for anim, profile in group:
                    result.kept.append((anim, profile))
                    result.needs_differentiation.add(anim.name)

        return result

    @staticmethod
    def find_duplicates(
        animations: List[Tuple[ParsedAnimation, AnimationProfile]],
    ) -> Dict[str, List[str]]:
        """Find groups of duplicate animation names by content hash.

        Returns:
            Dict mapping content hash to list of animation names.
        """
        hash_to_names: Dict[str, List[str]] = {}
        for anim, profile in animations:
            h = profile.content_hash
            if h not in hash_to_names:
                hash_to_names[h] = []
            hash_to_names[h].append(anim.name)

        # Only return groups with >1 member
        return {h: names for h, names in hash_to_names.items() if len(names) > 1}
