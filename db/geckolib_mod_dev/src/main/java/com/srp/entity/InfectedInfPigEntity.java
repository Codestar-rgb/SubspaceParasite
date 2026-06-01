package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfPigEntity extends Monster {

    // Part: infPig
    public static final String INF_PIG_GEO = "srp:geo/infected_infPig.geo.json";
    public static final String INF_PIG_TEXTURE = "srp:textures/entity/infected_infPig.png";
    // Part: infPigHead
    public static final String INF_PIG_HEAD_GEO = "srp:geo/infected_infPigHead.geo.json";
    public static final String INF_PIG_HEAD_TEXTURE = "srp:textures/entity/infected_infPigHead.png";

    public InfectedInfPigEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
