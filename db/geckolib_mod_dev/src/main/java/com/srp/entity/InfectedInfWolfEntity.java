package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfWolfEntity extends Monster {

    // Part: infWolf
    public static final String INF_WOLF_GEO = "srp:geo/infected_infWolf.geo.json";
    public static final String INF_WOLF_TEXTURE = "srp:textures/entity/infected_infWolf.png";
    // Part: infWolfHead
    public static final String INF_WOLF_HEAD_GEO = "srp:geo/infected_infWolfHead.geo.json";
    public static final String INF_WOLF_HEAD_TEXTURE = "srp:textures/entity/infected_infWolfHead.png";

    public InfectedInfWolfEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
