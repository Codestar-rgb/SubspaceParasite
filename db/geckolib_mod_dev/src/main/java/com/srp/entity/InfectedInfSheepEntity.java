package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfSheepEntity extends Monster {

    // Part: infSheep
    public static final String INF_SHEEP_GEO = "srp:geo/infected_infSheep.geo.json";
    public static final String INF_SHEEP_TEXTURE = "srp:textures/entity/infected_infSheep.png";
    // Part: infSheepHead
    public static final String INF_SHEEP_HEAD_GEO = "srp:geo/infected_infSheepHead.geo.json";
    public static final String INF_SHEEP_HEAD_TEXTURE = "srp:textures/entity/infected_infSheepHead.png";

    public InfectedInfSheepEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
