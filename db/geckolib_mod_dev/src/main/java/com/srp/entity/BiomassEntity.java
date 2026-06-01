package com.srp.entity;

import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class BiomassEntity extends PathfinderMob {

    // Part: biomassPod
    public static final String BIOMASS_POD_GEO = "srp:geo/misc_biomassPod.geo.json";
    public static final String BIOMASS_POD_TEXTURE = "srp:textures/entity/misc_biomassPod.png";
    // Part: biomassVenkrol
    public static final String BIOMASS_VENKROL_GEO = "srp:geo/misc_biomassVenkrol.geo.json";
    public static final String BIOMASS_VENKROL_TEXTURE = "srp:textures/entity/misc_biomassVenkrol.png";

    public BiomassEntity(EntityType<? extends PathfinderMob> type, Level level) {
        super(type, level);
    }
}
