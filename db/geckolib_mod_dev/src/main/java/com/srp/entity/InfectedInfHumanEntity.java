package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfHumanEntity extends Monster {

    // Part: infHuman
    public static final String INF_HUMAN_GEO = "srp:geo/infected_infHuman.geo.json";
    public static final String INF_HUMAN_TEXTURE = "srp:textures/entity/infected_infHuman.png";
    // Part: infHumanHead
    public static final String INF_HUMAN_HEAD_GEO = "srp:geo/infected_infHumanHead.geo.json";
    public static final String INF_HUMAN_HEAD_TEXTURE = "srp:textures/entity/infected_infHumanHead.png";

    public InfectedInfHumanEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
