package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfEndermanEntity extends Monster {

    // Part: infEnderman
    public static final String INF_ENDERMAN_GEO = "srp:geo/infected_infEnderman.geo.json";
    public static final String INF_ENDERMAN_TEXTURE = "srp:textures/entity/infected_infEnderman.png";
    // Part: infEndermanHead
    public static final String INF_ENDERMAN_HEAD_GEO = "srp:geo/infected_infEndermanHead.geo.json";
    public static final String INF_ENDERMAN_HEAD_TEXTURE = "srp:textures/entity/infected_infEndermanHead.png";

    public InfectedInfEndermanEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
