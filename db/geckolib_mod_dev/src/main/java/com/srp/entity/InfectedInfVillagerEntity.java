package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfVillagerEntity extends Monster {

    // Part: infVillager
    public static final String INF_VILLAGER_GEO = "srp:geo/infected_infVillager.geo.json";
    public static final String INF_VILLAGER_TEXTURE = "srp:textures/entity/infected_infVillager.png";
    // Part: infVillagerHead
    public static final String INF_VILLAGER_HEAD_GEO = "srp:geo/infected_infVillagerHead.geo.json";
    public static final String INF_VILLAGER_HEAD_TEXTURE = "srp:textures/entity/infected_infVillagerHead.png";

    public InfectedInfVillagerEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
