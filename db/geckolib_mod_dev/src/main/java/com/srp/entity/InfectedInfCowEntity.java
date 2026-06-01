package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfCowEntity extends Monster {

    // Part: infCow
    public static final String INF_COW_GEO = "srp:geo/infected_infCow.geo.json";
    public static final String INF_COW_TEXTURE = "srp:textures/entity/infected_infCow.png";
    // Part: infCowHead
    public static final String INF_COW_HEAD_GEO = "srp:geo/infected_infCowHead.geo.json";
    public static final String INF_COW_HEAD_TEXTURE = "srp:textures/entity/infected_infCowHead.png";

    public InfectedInfCowEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
