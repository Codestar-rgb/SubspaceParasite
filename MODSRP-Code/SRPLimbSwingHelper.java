package com.srparasites.client.model;

/**
 * SRPLimbSwingHelper - Reusable limbSwingAmount Lerp calculation.
 * ================================================================
 * Replicates MC 1.12.2's exponential decay smoothing for walk detection
 * in GeckoLib 1.20.1 animation controllers.
 *
 * <h3>Background</h3>
 * In MC 1.12.2, the limbSwingAmount field was smoothly interpolated
 * each frame using exponential decay:
 * <pre>
 *   limbSwingAmount += (targetAmount - limbSwingAmount) * 0.4F
 * </pre>
 * where targetAmount = horizontalDistance * 4.0F.
 *
 * <p>This smoothing prevents animation pop-in when entities start/stop
 * walking and provides the characteristic Minecraft movement feel.
 * Without it, walk animations would snap on/off instantly, looking jerky.</p>
 *
 * <h3>Usage in Entity Class</h3>
 * <pre>
 *   // Store as a field on the entity (per-entity tracking)
 *   private final SRPLimbSwingHelper limbSwingHelper = new SRPLimbSwingHelper();
 *
 *   // In tick() method, update the limb swing
 *   public void tick() {
 *       super.tick();
 *       limbSwingHelper.updateLimbSwing(
 *           (float) this.getDeltaMovement().horizontalDistance()
 *       );
 *   }
 *
 *   // In AnimationController callback, check walk state
 *   if (entity.getLimbSwingHelper().isWalking()) {
 *       event.getController().setAnimation(
 *           RawAnimation.begin().thenLoop("animation.model.walk")
 *       );
 *       return PlayState.CONTINUE;
 *   }
 * </pre>
 *
 * <h3>Usage in Model Class (singleton caveat)</h3>
 * <pre>
 *   // For single-entity scenarios, store on the model:
 *   private final SRPLimbSwingHelper limbSwingHelper = new SRPLimbSwingHelper();
 *
 *   // In registerControllers callback:
 *   limbSwingHelper.updateLimbSwing(
 *       entity.getDeltaMovement().horizontalDistance()
 *   );
 *   if (limbSwingHelper.isWalking()) { ... }
 * </pre>
 * <p><b>Note:</b> Model classes are singletons shared across all entities
 * of the same type. For multi-entity scenarios, use per-entity tracking
 * as shown above.</p>
 */
public class SRPLimbSwingHelper {

    /**
     * The exponential decay factor from MC 1.12.2's limbSwing interpolation.
     * A value of 0.4F means 40% of the difference is applied each tick,
     * creating smooth acceleration/deceleration of the limb swing.
     *
     * <p>Higher values = snappier transitions (less smooth)<br>
     * Lower values = smoother transitions (more sluggish)</p>
     */
    public static final float LERP_FACTOR = 0.4F;

    /**
     * The movement threshold for walk detection.
     * Values below this are considered stationary.
     * Matches vanilla MC behavior where very slow movement
     * doesn't trigger the walk animation cycle.
     */
    public static final float WALK_THRESHOLD = 0.01F;

    /**
     * Scaling factor applied to horizontal distance to get
     * the target limbSwingAmount. In vanilla MC, this converts
     * blocks/tick movement speed to animation speed.
     */
    public static final float MOVEMENT_SCALE = 4.0F;

    // Per-instance state
    private float prevLimbSwingAmount = 0.0F;
    private float limbSwingAmount = 0.0F;

    /**
     * Update the limbSwingAmount with exponential decay interpolation.
     *
     * @param horizontalDistance The entity's horizontal movement distance
     *                           per tick (from entity.getDeltaMovement().horizontalDistance())
     * @return The smoothed limbSwingAmount value
     */
    public float updateLimbSwing(float horizontalDistance) {
        float targetAmount = horizontalDistance * MOVEMENT_SCALE;
        this.prevLimbSwingAmount = this.limbSwingAmount;
        this.limbSwingAmount += (targetAmount - this.limbSwingAmount) * LERP_FACTOR;
        return this.limbSwingAmount;
    }

    /**
     * Check if the entity is currently walking based on smoothed limbSwingAmount.
     *
     * @return true if limbSwingAmount exceeds the walk threshold
     */
    public boolean isWalking() {
        return this.limbSwingAmount > WALK_THRESHOLD;
    }

    /**
     * Get the current smoothed limbSwingAmount.
     *
     * @return Current interpolated value
     */
    public float getLimbSwingAmount() {
        return this.limbSwingAmount;
    }

    /**
     * Get the previous tick's limbSwingAmount.
     * Useful for detecting state transitions (walk start/stop).
     *
     * @return Previous tick's interpolated value
     */
    public float getPrevLimbSwingAmount() {
        return this.prevLimbSwingAmount;
    }

    /**
     * Calculate the walk animation speed multiplier based on limbSwingAmount.
     * In MC 1.12.2, walk animation speed was proportional to limbSwingAmount,
     * capped at 1.0F. This provides the same behavior.
     *
     * @return Speed multiplier in range [0.0, 1.0]
     */
    public float getWalkSpeedMultiplier() {
        return Math.min(this.limbSwingAmount, 1.0F);
    }

    /**
     * Detect if the entity just started walking this tick.
     * Useful for triggering walk-start transition animations.
     *
     * @return true if walking now but was not walking last tick
     */
    public boolean startedWalking() {
        return this.limbSwingAmount > WALK_THRESHOLD
            && this.prevLimbSwingAmount <= WALK_THRESHOLD;
    }

    /**
     * Detect if the entity just stopped walking this tick.
     * Useful for triggering walk-stop transition animations.
     *
     * @return true if not walking now but was walking last tick
     */
    public boolean stoppedWalking() {
        return this.limbSwingAmount <= WALK_THRESHOLD
            && this.prevLimbSwingAmount > WALK_THRESHOLD;
    }

    /**
     * Reset the limbSwingAmount state (e.g., when entity is spawned or
     * changes dimension).
     */
    public void reset() {
        this.prevLimbSwingAmount = 0.0F;
        this.limbSwingAmount = 0.0F;
    }

    /**
     * Static helper: Calculate limbSwingAmount for a single tick without
     * maintaining state. Useful for one-off calculations or when state is
     * stored elsewhere.
     *
     * @param currentAmount The current limbSwingAmount
     * @param horizontalDistance The entity's horizontal movement distance
     * @return The new smoothed limbSwingAmount
     */
    public static float calculateLerp(float currentAmount, float horizontalDistance) {
        float targetAmount = horizontalDistance * MOVEMENT_SCALE;
        return currentAmount + (targetAmount - currentAmount) * LERP_FACTOR;
    }

    /**
     * Static helper: Check if a limbSwingAmount value indicates walking.
     *
     * @param limbSwingAmount The current smoothed value
     * @return true if the value exceeds the walk threshold
     */
    public static boolean isMoving(float limbSwingAmount) {
        return limbSwingAmount > WALK_THRESHOLD;
    }
}
