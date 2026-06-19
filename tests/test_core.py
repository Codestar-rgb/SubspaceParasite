#!/usr/bin/env python3
"""
Unit tests for the SubspaceParasite Converter (v6.8).

Run with: PYTHONPATH=. python -m pytest tests/ -v
Or:       PYTHONPATH=. python3 tests/test_core.py
"""

import sys
import os
import math
import unittest

# Ensure converter is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSafeEvaluator(unittest.TestCase):
    """Tests for engine/safe_evaluator.py — the AST-based expression evaluator."""

    def setUp(self):
        from engine.safe_evaluator import safe_eval, safe_eval_java, translate_java_to_python
        self.safe_eval = safe_eval
        self.safe_eval_java = safe_eval_java
        self.translate = translate_java_to_python

    def test_basic_arithmetic(self):
        self.assertAlmostEqual(self.safe_eval("1 + 2", {}), 3.0)
        self.assertAlmostEqual(self.safe_eval("1 + 2 * 3", {}), 7.0)
        self.assertAlmostEqual(self.safe_eval("(1 + 2) * 3", {}), 9.0)
        self.assertAlmostEqual(self.safe_eval("10 / 4", {}), 2.5)
        self.assertAlmostEqual(self.safe_eval("10 % 3", {}), 1.0)
        self.assertAlmostEqual(self.safe_eval("2 ** 3", {}), 8.0)

    def test_unary_ops(self):
        self.assertAlmostEqual(self.safe_eval("-5", {}), -5.0)
        self.assertAlmostEqual(self.safe_eval("+5", {}), 5.0)
        self.assertAlmostEqual(self.safe_eval("--5", {}), 5.0)

    def test_variable_lookup(self):
        self.assertAlmostEqual(self.safe_eval("x", {"x": 3.5}), 3.5)
        self.assertAlmostEqual(self.safe_eval("x + y", {"x": 1, "y": 2}), 3.0)
        self.assertAlmostEqual(self.safe_eval("x * y", {"x": 2.5, "y": 4}), 10.0)

    def test_unknown_variable_returns_zero(self):
        self.assertAlmostEqual(self.safe_eval("unknown_var", {}), 0.0)

    def test_math_functions(self):
        self.assertAlmostEqual(self.safe_eval("__sin(0)", {}), 0.0)
        self.assertAlmostEqual(self.safe_eval("__cos(0)", {}), 1.0)
        self.assertAlmostEqual(self.safe_eval("__sin(3.141592653589793)", {}), 0.0, places=6)
        self.assertAlmostEqual(self.safe_eval("__cos(3.141592653589793)", {}), -1.0)
        self.assertAlmostEqual(self.safe_eval("__sqrt(16)", {}), 4.0)
        self.assertAlmostEqual(self.safe_eval("__abs(-5)", {}), 5.0)
        self.assertAlmostEqual(self.safe_eval("__floor(3.7)", {}), 3.0)

    def test_java_translation(self):
        # Test Java syntax translation
        py = self.translate("0.2f * MathHelper.func_76126_a((float)(ageInTicks * 0.08f)) * 0.73f")
        self.assertNotIn("MathHelper", py)
        self.assertNotIn("(float)", py)
        self.assertIn("__sin", py)
        self.assertNotIn("0.2f", py)
        self.assertIn("0.2", py)

    def test_java_eval(self):
        # Full Java→Python→eval pipeline
        result = self.safe_eval_java(
            "0.2f * MathHelper.func_76126_a((float)(ageInTicks * 0.08f)) * 0.73f",
            {"ageInTicks": 1.5},
        )
        expected = 0.2 * math.sin(1.5 * 0.08) * 0.73
        self.assertAlmostEqual(result, expected, places=6)

    def test_chained_assignment(self):
        # f2 = 0.9f * ... → take last segment
        result = self.safe_eval_java("f2 = 0.9f * __cos(0)", {})
        self.assertAlmostEqual(result, 0.9, places=6)

    def test_pi_constant(self):
        result = self.safe_eval("__cos(PI)", {})
        self.assertAlmostEqual(result, -1.0, places=6)

    # Security tests — these should all return 0.0 (blocked)
    def test_security_attribute_access_blocked(self):
        self.assertEqual(self.safe_eval("().__class__", {}), 0.0)

    def test_security_import_blocked(self):
        self.assertEqual(self.safe_eval("__import__('os')", {}), 0.0)

    def test_security_open_blocked(self):
        self.assertEqual(self.safe_eval("open('/etc/passwd')", {}), 0.0)

    def test_security_subscript_blocked(self):
        self.assertEqual(self.safe_eval("[1,2,3][0]", {}), 0.0)

    def test_security_lambda_blocked(self):
        self.assertEqual(self.safe_eval("(lambda: 1)()", {}), 0.0)

    def test_security_comprehension_blocked(self):
        self.assertEqual(self.safe_eval("[x for x in range(10)]", {}), 0.0)

    def test_empty_expression(self):
        self.assertEqual(self.safe_eval("", {}), 0.0)
        self.assertEqual(self.safe_eval("   ", {}), 0.0)


class TestAnimationDedup(unittest.TestCase):
    """Tests for engine/mve_data_loader.py — visual similarity dedup."""

    def setUp(self):
        from engine.mve_data_loader import _animations_visually_similar
        from core.types import AnimationIR, BoneAnimationIR, KeyframeData, AxisValue
        self._sim = _animations_visually_similar
        self._AnimationIR = AnimationIR
        self._BoneAnimationIR = BoneAnimationIR
        self._KeyframeData = KeyframeData
        self._AxisValue = AxisValue

    def _make_anim(self, bone_name, values, length=1.0):
        """Helper: create an AnimationIR with one bone having rotation keyframes."""
        kfs = []
        for t, v in enumerate(values):
            kfs.append(self._KeyframeData(
                time=t * 0.1,
                channel="rotation",
                x=self._AxisValue.explicit_val(v),
                y=self._AxisValue.explicit_val(0),
                z=self._AxisValue.explicit_val(0),
                easing="linear",
                interpolation="linear",
            ))
        bone = self._BoneAnimationIR(bone_name=bone_name, keyframes=kfs)
        return self._AnimationIR(name="test", loop="loop", length=length, bones={bone_name: bone})

    def test_identical_animations_are_similar(self):
        a1 = self._make_anim("bone1", [0, 5, 10, 5, 0])
        a2 = self._make_anim("bone1", [0, 5, 10, 5, 0])
        self.assertTrue(self._sim(a1, a2, threshold=2.0))

    def test_different_bone_sets_not_similar(self):
        a1 = self._make_anim("bone1", [0, 5, 10])
        a2 = self._make_anim("bone2", [0, 5, 10])
        self.assertFalse(self._sim(a1, a2, threshold=2.0))

    def test_small_difference_is_similar(self):
        a1 = self._make_anim("bone1", [0, 5, 10, 5, 0])
        a2 = self._make_anim("bone1", [0, 6, 11, 6, 0])  # 1 degree diff
        self.assertTrue(self._sim(a1, a2, threshold=2.0))

    def test_large_difference_not_similar(self):
        a1 = self._make_anim("bone1", [0, 5, 10, 5, 0])
        a2 = self._make_anim("bone1", [0, 15, 20, 15, 0])  # 10 degree diff
        self.assertFalse(self._sim(a1, a2, threshold=2.0))

    def test_threshold_boundary(self):
        a1 = self._make_anim("bone1", [0, 0, 0])
        a2 = self._make_anim("bone1", [0, 3, 0])  # 3 degree diff
        # threshold=2 → not similar
        self.assertFalse(self._sim(a1, a2, threshold=2.0))
        # threshold=5 → similar
        self.assertTrue(self._sim(a1, a2, threshold=5.0))


class TestStateExtraction(unittest.TestCase):
    """Tests for engine/java_analyzer.py — state machine parsing."""

    def setUp(self):
        from engine.java_analyzer import _extract_states
        from engine.mve_capture import _split_still_ani_branches
        self._extract_states = _extract_states
        self._split_still = _split_still_ani_branches

    def test_no_state_machine(self):
        """Body without getParasiteStatus returns single state 0."""
        body = "this.bone.field = 1.0f;"
        states = self._extract_states(body)
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].state_value, 0)

    def test_single_state(self):
        body = """
        byte i = parasite.getParasiteStatus();
        if (i == 0) {
            this.bone.field = 1.0f;
        }
        """
        states = self._extract_states(body)
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].state_value, 0)

    def test_multiple_states(self):
        body = """
        byte i = parasite.getParasiteStatus();
        if (i == 0) {
            this.bone.field = 1.0f;
        } else if (i == 1) {
            this.bone.field = 2.0f;
        } else if (i == 10) {
            this.bone.field = 3.0f;
        }
        """
        states = self._extract_states(body)
        self.assertEqual(len(states), 3)
        self.assertEqual(states[0].state_value, 0)
        self.assertEqual(states[1].state_value, 1)
        self.assertEqual(states[2].state_value, 10)

    def test_pre_state_assignments_included(self):
        """Assignments before the first if(state==N) should be in each state's body."""
        body = """
        float f1 = MathHelper.func_76134_b(ageInTicks * 0.1f);
        this.bone.field = f1;
        byte i = parasite.getParasiteStatus();
        if (i == 0) {
            this.bone2.field = f1;
        }
        """
        states = self._extract_states(body)
        self.assertEqual(len(states), 1)
        # The pre-state assignment should be in the state body
        self.assertIn("this.bone.field", states[0].body)

    def test_split_still_ani_branches(self):
        """getStillAni split should separate walk and idle branches."""
        body = """
        if (!parasite.getStillAni()) {
            this.swingX(this.bone, 0.3f, 1.0f, 1, limbSwing, limbSwingAmount);
        } else {
            this.bone.field = MathHelper.func_76134_b(ageInTicks * 0.1f) * 0.5f;
        }
        this.shared.field = 1.0f;
        """
        walk_body, idle_body = self._split_still(body)
        self.assertIn("swingX", walk_body)
        self.assertIn("func_76134_b", idle_body)
        # Shared code should be in both
        self.assertIn("this.shared.field", walk_body)
        self.assertIn("this.shared.field", idle_body)

    def test_no_getStillAni_returns_same_body(self):
        body = "this.bone.field = 1.0f;"
        walk, idle = self._split_still(body)
        self.assertEqual(walk, body)
        self.assertEqual(idle, body)


class TestConfig(unittest.TestCase):
    """Tests for config.py — path configuration."""

    def test_config_paths_exist_or_have_env_override(self):
        import config
        # Paths should be strings
        self.assertIsInstance(config.INPUT_DIR, str)
        self.assertIsInstance(config.DECOMPILED_DIR, str)
        self.assertIsInstance(config.MVE_DATA_DIR, str)
        self.assertIsInstance(config.OUTPUT_DIR, str)

    def test_dedup_threshold_is_float(self):
        import config
        self.assertIsInstance(config.DEDUP_THRESHOLD, float)
        self.assertGreater(config.DEDUP_THRESHOLD, 0)

    def test_mve_sample_count_is_int(self):
        import config
        self.assertIsInstance(config.MVE_SAMPLE_COUNT, int)
        self.assertGreater(config.MVE_SAMPLE_COUNT, 0)


class TestCoordinateTransform(unittest.TestCase):
    """Tests for core/coords.py — RH→LH coordinate transform."""

    def test_axis_sign_flip(self):
        from engine.mve_capture import AXIS_SIGN_FLIP
        # X axis: no flip
        self.assertEqual(AXIS_SIGN_FLIP["x"], 1)
        # Y axis: flip (RH Y-down → LH Y-up)
        self.assertEqual(AXIS_SIGN_FLIP["y"], -1)
        # Z axis: flip
        self.assertEqual(AXIS_SIGN_FLIP["z"], -1)

    def test_rad2deg_conversion(self):
        from engine.mve_capture import RAD2DEG
        self.assertAlmostEqual(RAD2DEG, 57.29577951308232)
        self.assertAlmostEqual(RAD2DEG * math.pi, 180.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
