"""
Molang Injector (v6.9.17)

Maps SRP runtime method calls to GeckoLib Molang expressions, enabling
dynamic animation behavior (growth, speed, attack) instead of fixed constants.

Instead of evaluating getBODY() as a constant, generates Molang expressions
that GeckoLib evaluates at runtime.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Runtime method -> Molang expression mapping
RUNTIME_VAR_MAP = {
    'getBODY': 'v.body',
    'getFloorTimer': 'v.floor_timer',
    'getAttackTimer': 'v.attack_timer',
    'shakingC': 'v.shaking_count',
    'getStillAni': 'v.still_ani',
    'getCloneC': 'v.clone_c',
    'showC': 'v.show_c',
    'getParasiteStatus': 'v.parasite_status',
    'getLeft': 'v.left',
    'getRight': 'v.right',
    'getHead': 'v.head',
    'getaaa': 'query.modified_move_speed',
    'raining': 'query.is_raining',
}

# Molang expressions for common runtime patterns
MOLANG_PATTERNS = {
    # limbSwingAmount replacement: use move speed
    'limbSwingAmount': 'math.clamp(query.modified_move_speed * 20, 0, 1)',
    # netHeadYaw/headPitch: use look direction
    'netHeadYaw': 'query.y_head_rotation',
    'headPitch': 'query.target_x_rotation',
}


def should_use_molang(expr: str) -> bool:
    """Check if an expression contains runtime method calls that need Molang."""
    for method in RUNTIME_VAR_MAP:
        if method in expr:
            return True
    return False


def inject_molang(expr: str) -> Optional[str]:
    """Replace runtime method calls with Molang expressions.

    Returns the Molang-enhanced expression, or None if not injectable
    (falls back to constant evaluation).
    """
    molang_expr = expr

    # Replace getBODY() etc with Molang variables
    for method, molang in RUNTIME_VAR_MAP.items():
        # Pattern: parasite.getBODY() or entity.getBODY()
        molang_expr = re.sub(
            rf'\w+\.{method}\(\)',
            molang,
            molang_expr
        )

    # Check if any runtime calls remain
    has_remaining = False
    for method in RUNTIME_VAR_MAP:
        if re.search(rf'\w+\.{method}\(\)', molang_expr):
            has_remaining = True
            break

    if has_remaining:
        return None  # Can't fully convert to Molang

    # Convert Java math to Molang
    molang_expr = molang_expr.replace('MathHelper.func_76126_a', 'math.sin')
    molang_expr = molang_expr.replace('MathHelper.func_76134_b', 'math.cos')
    molang_expr = molang_expr.replace('MathHelper.func_76134_d', 'math.cos')
    molang_expr = molang_expr.replace('Math.PI', str(3.141592653589793))

    # Remove Java float suffix
    molang_expr = re.sub(r'(\d+(?:\.\d+)?)[fF]', r'\1', molang_expr)
    molang_expr = molang_expr.replace('(float)', '').replace('(int)', '')

    # Replace limbSwing/ageInTicks (these ARE available as Molang)
    # ageInTicks -> query.anim_time * 20
    # limbSwing -> query.life_time * 20 (approximate)
    molang_expr = molang_expr.replace('ageInTicks', 'query.anim_time * 20')
    # limbSwing is not directly available; keep as variable
    molang_expr = molang_expr.replace('limbSwing', 'v.limb_swing')

    return molang_expr


def generate_molang_keyframe(time: float, molang_expr: str, channel: str) -> dict:
    """Generate a bbmodel keyframe with Molang expression."""
    return {
        "channel": channel,
        "data_points": [{
            "x": molang_expr,
            "y": "0.0",
            "z": "0.0",
        }],
        "uuid": "",  # Will be filled by exporter
        "time": round(time, 6),
        "color": -1,
        "interpolation": "catmullrom",
    }
