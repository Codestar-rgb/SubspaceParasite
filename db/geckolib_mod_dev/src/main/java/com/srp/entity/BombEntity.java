package com.srp.entity;

import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class BombEntity extends PathfinderMob {

    // Part: bombHost
    public static final String BOMB_HOST_GEO = "srp:geo/misc_bombHost.geo.json";
    public static final String BOMB_HOST_TEXTURE = "srp:textures/entity/misc_bombHost.png";
    // Part: bombJinjo
    public static final String BOMB_JINJO_GEO = "srp:geo/misc_bombJinjo.geo.json";
    public static final String BOMB_JINJO_TEXTURE = "srp:textures/entity/misc_bombJinjo.png";
    // Part: bombOmboo
    public static final String BOMB_OMBOO_GEO = "srp:geo/misc_bombOmboo.geo.json";
    public static final String BOMB_OMBOO_TEXTURE = "srp:textures/entity/misc_bombOmboo.png";

    public BombEntity(EntityType<? extends PathfinderMob> type, Level level) {
        super(type, level);
    }
}
