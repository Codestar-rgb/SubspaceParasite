package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfPlayerEntity extends Monster {

    // Part: infPlayer
    public static final String INF_PLAYER_GEO = "srp:geo/infected_infPlayer.geo.json";
    public static final String INF_PLAYER_TEXTURE = "srp:textures/entity/infected_infPlayer.png";
    // Part: infPlayerHead
    public static final String INF_PLAYER_HEAD_GEO = "srp:geo/infected_infPlayerHead.geo.json";
    public static final String INF_PLAYER_HEAD_TEXTURE = "srp:textures/entity/infected_infPlayerHead.png";

    public InfectedInfPlayerEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
