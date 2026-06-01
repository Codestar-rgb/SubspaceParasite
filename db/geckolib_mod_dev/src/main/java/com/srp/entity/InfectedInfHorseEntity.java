package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfHorseEntity extends Monster {

    // Part: infHorse
    public static final String INF_HORSE_GEO = "srp:geo/infected_infHorse.geo.json";
    public static final String INF_HORSE_TEXTURE = "srp:textures/entity/infected_infHorse.png";
    // Part: infHorseHead
    public static final String INF_HORSE_HEAD_GEO = "srp:geo/infected_infHorseHead.geo.json";
    public static final String INF_HORSE_HEAD_TEXTURE = "srp:textures/entity/infected_infHorseHead.png";

    public InfectedInfHorseEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
