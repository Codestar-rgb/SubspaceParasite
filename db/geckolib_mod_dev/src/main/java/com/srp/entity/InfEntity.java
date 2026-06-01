package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfEntity extends Monster {

    // Part: infBear
    public static final String INF_BEAR_GEO = "srp:geo/infected_infBear.geo.json";
    public static final String INF_BEAR_TEXTURE = "srp:textures/entity/infected_infBear.png";
    // Part: infSquid
    public static final String INF_SQUID_GEO = "srp:geo/infected_infSquid.geo.json";
    public static final String INF_SQUID_TEXTURE = "srp:textures/entity/infected_infSquid.png";

    public InfEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
