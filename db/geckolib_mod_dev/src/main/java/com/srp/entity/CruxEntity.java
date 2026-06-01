package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class CruxEntity extends Monster {

    // Part: cruxA
    public static final String CRUX_A_GEO = "srp:geo/crude_cruxA.geo.json";
    public static final String CRUX_A_TEXTURE = "srp:textures/entity/crude_cruxA.png";
    // Part: cruxB
    public static final String CRUX_B_GEO = "srp:geo/crude_cruxB.geo.json";
    public static final String CRUX_B_TEXTURE = "srp:textures/entity/crude_cruxB.png";

    public CruxEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
