package com.srp.entity;

import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class OrbEntity extends PathfinderMob {

    // Part: orbScary
    public static final String ORB_SCARY_GEO = "srp:geo/misc_orbScary.geo.json";
    public static final String ORB_SCARY_TEXTURE = "srp:textures/entity/misc_orbScary.png";
    // Part: orbVoid
    public static final String ORB_VOID_GEO = "srp:geo/misc_orbVoid.geo.json";
    public static final String ORB_VOID_TEXTURE = "srp:textures/entity/misc_orbVoid.png";

    public OrbEntity(EntityType<? extends PathfinderMob> type, Level level) {
        super(type, level);
    }
}
