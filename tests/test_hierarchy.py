#!/usr/bin/env python3
"""
test_hierarchy.py - Bone Hierarchy Regression Tests
====================================================
Tests for the MinecraftModelMigrator-Pro converter's bone hierarchy
and pivot relative-to-parent calculation.

Validates:
  1. Simple parent-child model: pivots are relative to parent
  2. Kirin key bone spot-check: specific bone pivots match expected values
  3. Symmetric bone test: left/right bones have symmetric pivots
  4. Animation binding test: animation bone names exist in geo.json
  5. Root pivot offset test: top-level bones are relative to root.pivot
"""

import json
import math
import os
import sys

# Add converter to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'converter'))

from model_converter import ModelConverter
from core_math import convert_model_pos, convert_model_cube_origin


def approx_eq(a, b, tol=0.01):
    """Check if two values are approximately equal."""
    return abs(a - b) < tol


def vec_approx_eq(v1, v2, tol=0.01):
    """Check if two 3D vectors are approximately equal."""
    return all(approx_eq(a, b, tol) for a, b in zip(v1, v2))


# ============================================================================
# Test 1: Simple Parent-Child Model
# ============================================================================

def test_simple_parent_child():
    """
    Test with a simple 2-bone hierarchy:
      - Parent bone: pivot at (0, 10, 5) in MC 1.12.2, no cube
      - Child bone: pivot at (0, 2, 0) relative to parent, one 1x1x1 cube

    After conversion:
      - Parent pivot should be (0, -10, -5) - root.pivot = (0, -10-24, -5) relative to root
      - Child pivot should be convert_model_pos(0, 2, 0) = (0, -2, 0) relative to parent
    """
    test_java = """
    public class TestModel extends ModelBase {
        public ModelRenderer parent;
        public ModelRenderer child;

        public TestModel() {
            this.field_78090_t = 64;
            this.field_78089_u = 32;
            this.parent = new ModelRenderer((ModelBase)this, 0, 0);
            this.parent.func_78793_a(0.0f, 10.0f, 5.0f);
            this.child = new ModelRenderer((ModelBase)this, 0, 0);
            this.child.func_78793_a(0.0f, 2.0f, 0.0f);
            this.child.func_78790_a(0.0f, 0.0f, 0.0f, 1, 1, 1, 0.0f);
            this.parent.func_78792_a(this.child);
        }
    }
    """

    converter = ModelConverter()
    result = converter.convert(test_java, "model.test")

    bones = result['geo_json']['model']['bones']
    bone_map = {b['name']: b for b in bones}

    # Verify root
    root = bone_map['root']
    assert root['pivot'] == [0.0, 24.0, 0.0], f"Root pivot wrong: {root['pivot']}"

    # Verify parent (top-level, parent=root)
    parent = bone_map['parent']
    # MC 1.12.2 abs pivot: (0, 10, 5)
    # convert_model_pos: (0, -10, -5)
    # Relative to root [0, 24, 0]: (0, -10-24, -5) = (0, -34, -5)
    expected_parent_pivot = [0.0, -34.0, -5.0]
    assert vec_approx_eq(parent['pivot'], expected_parent_pivot), \
        f"Parent pivot wrong: {parent['pivot']}, expected: {expected_parent_pivot}"
    assert parent['parent'] == 'root', f"Parent parent wrong: {parent.get('parent')}"

    # Verify child (child of parent)
    child = bone_map['child']
    # MC 1.12.2 relative pivot: (0, 2, 0)
    # convert_model_pos: (0, -2, 0) - this is relative to parent, unchanged
    expected_child_pivot = [0.0, -2.0, 0.0]
    assert vec_approx_eq(child['pivot'], expected_child_pivot), \
        f"Child pivot wrong: {child['pivot']}, expected: {expected_child_pivot}"
    assert child['parent'] == 'parent', f"Child parent wrong: {child.get('parent')}"

    # Verify world position chain
    # Root world: [0, 24, 0]
    # Parent world: root + parent.pivot = [0, 24+(-34), -5] = [0, -10, -5]
    #   = convert_model_pos(0, 10, 5) = (0, -10, -5) ✓
    parent_world = [root['pivot'][i] + parent['pivot'][i] for i in range(3)]
    expected_parent_world = [0.0, -10.0, -5.0]
    assert vec_approx_eq(parent_world, expected_parent_world), \
        f"Parent world position wrong: {parent_world}, expected: {expected_parent_world}"

    # Child world (no rotation): parent_world + child.pivot = [0, -10+(-2), -5+0] = [0, -12, -5]
    #   = convert_model_pos(0, 12, 5) = (0, -12, -5) ✓ (MC abs: parent(0,10,5) + child(0,2,0) = (0,12,5))
    child_world = [parent_world[i] + child['pivot'][i] for i in range(3)]
    expected_child_world = [0.0, -12.0, -5.0]
    assert vec_approx_eq(child_world, expected_child_world), \
        f"Child world position wrong: {child_world}, expected: {expected_child_world}"

    print("  [PASS] test_simple_parent_child")


# ============================================================================
# Test 2: Kirin Key Bone Spot-Check
# ============================================================================

def test_kirin_key_bones():
    """
    Spot-check key bones from the Kirin model against manually computed expected values.

    From ModelKirin.java:
      - mainbody: setRotationPoint(0, -77, -16), no parent (top-level)
      - bodym: setRotationPoint(0, 0, 0), parent=mainbody
      - jointURAX: setRotationPoint(12, 11, 3), parent=mainbody
      - jointULAX: setRotationPoint(-12, 11, 3), parent=mainbody

    Expected after conversion:
      - mainbody pivot (relative to root [0,24,0]):
          convert_model_pos(0, -77, -16) - root = (0, 77, 16) - (0, 24, 0) = (0, 53, 16)
      - bodym pivot (relative to mainbody):
          convert_model_pos(0, 0, 0) = (0, 0, 0)
      - jointURAX pivot (relative to mainbody):
          convert_model_pos(12, 11, 3) = (12, -11, -3)
      - jointULAX pivot (relative to mainbody):
          convert_model_pos(-12, 11, 3) = (-12, -11, -3)
    """
    kirin_path = os.path.join(os.path.dirname(__file__), '..', 'decompiled',
                               'com', 'dhanantry', 'scapeandrunparasites',
                               'client', 'model', 'entity', 'derived',
                               'ModelKirin.java')
    if not os.path.isfile(kirin_path):
        print("  [SKIP] test_kirin_key_bones - ModelKirin.java not found")
        return

    with open(kirin_path, 'r') as f:
        java_source = f.read()

    converter = ModelConverter()
    result = converter.convert(java_source, "model.kirin")

    bones = result['geo_json']['model']['bones']
    bone_map = {b['name']: b for b in bones}

    # Check mainbody pivot (top-level, relative to root)
    mainbody = bone_map['mainbody']
    expected_mainbody = [0.0, 53.0, 16.0]
    assert vec_approx_eq(mainbody['pivot'], expected_mainbody), \
        f"mainbody pivot wrong: {mainbody['pivot']}, expected: {expected_mainbody}"

    # Check bodym pivot (child of mainbody)
    bodym = bone_map['bodym']
    expected_bodym = [0.0, 0.0, 0.0]
    assert vec_approx_eq(bodym['pivot'], expected_bodym), \
        f"bodym pivot wrong: {bodym['pivot']}, expected: {expected_bodym}"

    # Check jointURAX pivot (child of mainbody)
    jointURAX = bone_map['jointURAX']
    expected_urax = [12.0, -11.0, -3.0]
    assert vec_approx_eq(jointURAX['pivot'], expected_urax), \
        f"jointURAX pivot wrong: {jointURAX['pivot']}, expected: {expected_urax}"

    # Check jointULAX pivot (child of mainbody)
    jointULAX = bone_map['jointULAX']
    expected_ulax = [-12.0, -11.0, -3.0]
    assert vec_approx_eq(jointULAX['pivot'], expected_ulax), \
        f"jointULAX pivot wrong: {jointULAX['pivot']}, expected: {expected_ulax}"

    # Check mainbody world position
    root = bone_map['root']
    mainbody_world = [root['pivot'][i] + mainbody['pivot'][i] for i in range(3)]
    expected_world = [0.0, 77.0, 16.0]
    assert vec_approx_eq(mainbody_world, expected_world), \
        f"mainbody world position wrong: {mainbody_world}, expected: {expected_world}"

    print("  [PASS] test_kirin_key_bones")


# ============================================================================
# Test 3: Symmetric Bone Test
# ============================================================================

def test_symmetric_bones():
    """
    Test that left/right symmetric bones have pivots that are mirror images
    in the X axis (X components are negatives of each other, Y and Z same).

    From ModelKirin.java:
      - jointURAX: setRotationPoint(12, 11, 3)  (upper right)
      - jointULAX: setRotationPoint(-12, 11, 3)  (upper left)
      - jointMRAX: setRotationPoint(10, -1, 18)  (middle right)
      - jointMLAX: setRotationPoint(-10, -1, 18)  (middle left)
      - jointDRAX: setRotationPoint(6, -12, 34)  (down right)
      - jointDLAX: setRotationPoint(-6, -12, 34)  (down left)
    """
    kirin_path = os.path.join(os.path.dirname(__file__), '..', 'decompiled',
                               'com', 'dhanantry', 'scapeandrunparasites',
                               'client', 'model', 'entity', 'derived',
                               'ModelKirin.java')
    if not os.path.isfile(kirin_path):
        print("  [SKIP] test_symmetric_bones - ModelKirin.java not found")
        return

    with open(kirin_path, 'r') as f:
        java_source = f.read()

    converter = ModelConverter()
    result = converter.convert(java_source, "model.kirin")

    bones = result['geo_json']['model']['bones']
    bone_map = {b['name']: b for b in bones}

    # Check symmetric pairs
    symmetric_pairs = [
        ('jointURAX', 'jointULAX'),  # Upper right/left arm X
        ('jointMRAX', 'jointMLAX'),  # Middle right/left arm X
        ('jointDRAX', 'jointDLAX'),  # Down right/left arm X
    ]

    for right_name, left_name in symmetric_pairs:
        right = bone_map[right_name]
        left = bone_map[left_name]

        # X components should be negatives of each other
        assert approx_eq(right['pivot'][0], -left['pivot'][0]), \
            f"{right_name}.x = {right['pivot'][0]}, but -{left_name}.x = {-left['pivot'][0]}"

        # Y components should be equal
        assert approx_eq(right['pivot'][1], left['pivot'][1]), \
            f"{right_name}.y = {right['pivot'][1]}, but {left_name}.y = {left['pivot'][1]}"

        # Z components should be equal
        assert approx_eq(right['pivot'][2], left['pivot'][2]), \
            f"{right_name}.z = {right['pivot'][2]}, but {left_name}.z = {left['pivot'][2]}"

    print("  [PASS] test_symmetric_bones")


# ============================================================================
# Test 4: Animation Binding Test
# ============================================================================

def test_animation_binding():
    """
    Check that all bone names referenced in the .animation.json exist
    in the .geo.json bone list.
    """
    kirin_path = os.path.join(os.path.dirname(__file__), '..', 'decompiled',
                               'com', 'dhanantry', 'scapeandrunparasites',
                               'client', 'model', 'entity', 'derived',
                               'ModelKirin.java')
    anim_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'kirin.animation.json')

    if not os.path.isfile(kirin_path) or not os.path.isfile(anim_path):
        print("  [SKIP] test_animation_binding - files not found")
        return

    with open(kirin_path, 'r') as f:
        java_source = f.read()

    converter = ModelConverter()
    result = converter.convert(java_source, "model.kirin")

    # Get bone names from geo.json
    bones = result['geo_json']['model']['bones']
    geo_bone_names = set(b['name'] for b in bones)

    # Get bone names from animation.json
    with open(anim_path, 'r') as f:
        anim_json = json.load(f)

    anim_bone_names = set()
    for anim_key, anim_data in anim_json.get('animations', {}).items():
        if 'bones' in anim_data:
            anim_bone_names.update(anim_data['bones'].keys())

    # Check that all animation bone names exist in geo.json
    missing = anim_bone_names - geo_bone_names
    assert len(missing) == 0, \
        f"Animation references bones not in geo.json: {missing}"

    print(f"  [PASS] test_animation_binding ({len(anim_bone_names)} animated bones verified)")


# ============================================================================
# Test 5: Root Pivot Offset Test
# ============================================================================

def test_root_pivot_offset():
    """
    Test that top-level bones (parent=root) have pivots that are relative
    to root.pivot, not absolute coordinates.

    The root bone pivot is [0, 24, 0]. A top-level bone with absolute
    position (0, 77, 16) should have pivot (0, 53, 16) relative to root.
    """
    test_java = """
    public class TestOffset extends ModelBase {
        public ModelRenderer body;

        public TestOffset() {
            this.field_78090_t = 64;
            this.field_78089_u = 32;
            this.body = new ModelRenderer((ModelBase)this, 0, 0);
            this.body.func_78793_a(0.0f, -24.0f, 0.0f);
            this.body.func_78790_a(-4.0f, -8.0f, -4.0f, 8, 8, 8, 0.0f);
        }
    }
    """

    converter = ModelConverter()
    result = converter.convert(test_java, "model.test_offset")

    bones = result['geo_json']['model']['bones']
    bone_map = {b['name']: b for b in bones}

    root = bone_map['root']
    body = bone_map['body']

    # MC 1.12.2: body setRotationPoint(0, -24, 0) → absolute
    # convert_model_pos(0, -24, 0) = (0, 24, 0) → absolute in new system
    # Relative to root [0, 24, 0]: (0, 24-24, 0) = (0, 0, 0)
    expected_pivot = [0.0, 0.0, 0.0]
    assert vec_approx_eq(body['pivot'], expected_pivot), \
        f"Body pivot wrong: {body['pivot']}, expected: {expected_pivot}"

    # World position should be (0, 24, 0)
    world_pos = [root['pivot'][i] + body['pivot'][i] for i in range(3)]
    expected_world = [0.0, 24.0, 0.0]
    assert vec_approx_eq(world_pos, expected_world), \
        f"Body world position wrong: {world_pos}, expected: {expected_world}"

    print("  [PASS] test_root_pivot_offset")


# ============================================================================
# Test 6: Deep Hierarchy Test
# ============================================================================

def test_deep_hierarchy():
    """
    Test a 3-level hierarchy: root → parent → child → grandchild
    Ensures pivots are correctly relative at each level.
    """
    test_java = """
    public class TestDeep extends ModelBase {
        public ModelRenderer parent;
        public ModelRenderer child;
        public ModelRenderer grandchild;

        public TestDeep() {
            this.field_78090_t = 64;
            this.field_78089_u = 32;
            this.parent = new ModelRenderer((ModelBase)this, 0, 0);
            this.parent.func_78793_a(5.0f, -20.0f, -10.0f);
            this.parent.func_78790_a(-2.0f, -2.0f, -2.0f, 4, 4, 4, 0.0f);
            this.child = new ModelRenderer((ModelBase)this, 0, 0);
            this.child.func_78793_a(3.0f, 5.0f, -2.0f);
            this.child.func_78790_a(-1.0f, -1.0f, -1.0f, 2, 2, 2, 0.0f);
            this.grandchild = new ModelRenderer((ModelBase)this, 0, 0);
            this.grandchild.func_78793_a(0.0f, -3.0f, 1.0f);
            this.grandchild.func_78790_a(-0.5f, -0.5f, -0.5f, 1, 1, 1, 0.0f);
            this.parent.func_78792_a(this.child);
            this.child.func_78792_a(this.grandchild);
        }
    }
    """

    converter = ModelConverter()
    result = converter.convert(test_java, "model.test_deep")

    bones = result['geo_json']['model']['bones']
    bone_map = {b['name']: b for b in bones}

    root = bone_map['root']
    parent = bone_map['parent']
    child = bone_map['child']
    grandchild = bone_map['grandchild']

    # Parent: MC abs (5, -20, -10) → convert_model_pos(5, -20, -10) = (5, 20, 10)
    # Relative to root [0, 24, 0]: (5, 20-24, 10) = (5, -4, 10)
    assert vec_approx_eq(parent['pivot'], [5.0, -4.0, 10.0]), \
        f"Parent pivot wrong: {parent['pivot']}"

    # Child: MC relative (3, 5, -2) → convert_model_pos(3, 5, -2) = (3, -5, 2)
    assert vec_approx_eq(child['pivot'], [3.0, -5.0, 2.0]), \
        f"Child pivot wrong: {child['pivot']}"

    # Grandchild: MC relative (0, -3, 1) → convert_model_pos(0, -3, 1) = (0, 3, -1)
    assert vec_approx_eq(grandchild['pivot'], [0.0, 3.0, -1.0]), \
        f"Grandchild pivot wrong: {grandchild['pivot']}"

    # Verify world positions
    parent_world = [root['pivot'][i] + parent['pivot'][i] for i in range(3)]
    assert vec_approx_eq(parent_world, [5.0, 20.0, 10.0]), \
        f"Parent world wrong: {parent_world}"

    # Note: child world = parent_world + child.pivot only when parent has no rotation
    # With rotation, it would be parent_world + R_parent * child.pivot

    print("  [PASS] test_deep_hierarchy")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Bone Hierarchy Regression Tests")
    print("=" * 60)
    print()

    tests = [
        test_simple_parent_child,
        test_kirin_key_bones,
        test_symmetric_bones,
        test_animation_binding,
        test_root_pivot_offset,
        test_deep_hierarchy,
    ]

    passed = 0
    failed = 0
    skipped = 0

    for test in tests:
        name = test.__name__
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
