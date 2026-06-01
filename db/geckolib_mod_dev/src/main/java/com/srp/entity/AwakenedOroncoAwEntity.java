package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class AwakenedOroncoAwEntity extends Monster {

    // Part: oroncoAW
    public static final String ORONCO_A_W_GEO = "srp:geo/awakened_oroncoAW.geo.json";
    public static final String ORONCO_A_W_TEXTURE = "srp:textures/entity/awakened_oroncoAW.png";
    // Part: oroncoAWFL
    public static final String ORONCO_A_W_F_L_GEO = "srp:geo/awakened_oroncoAWFL.geo.json";
    public static final String ORONCO_A_W_F_L_TEXTURE = "srp:textures/entity/awakened_oroncoAWFL.png";

    public AwakenedOroncoAwEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
