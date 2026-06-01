package com.srp.entity;

import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class TendrilEntity extends PathfinderMob {

    // Part: tendrilAnged
    public static final String TENDRIL_ANGED_GEO = "srp:geo/misc_tendrilAnged.geo.json";
    public static final String TENDRIL_ANGED_TEXTURE = "srp:textures/entity/misc_tendrilAnged.png";
    // Part: tendrilBano
    public static final String TENDRIL_BANO_GEO = "srp:geo/misc_tendrilBano.geo.json";
    public static final String TENDRIL_BANO_TEXTURE = "srp:textures/entity/misc_tendrilBano.png";
    // Part: tendrilCanra
    public static final String TENDRIL_CANRA_GEO = "srp:geo/misc_tendrilCanra.geo.json";
    public static final String TENDRIL_CANRA_TEXTURE = "srp:textures/entity/misc_tendrilCanra.png";
    // Part: tendrilDragonELW
    public static final String TENDRIL_DRAGON_E_L_W_GEO = "srp:geo/misc_tendrilDragonELW.geo.json";
    public static final String TENDRIL_DRAGON_E_L_W_TEXTURE = "srp:textures/entity/misc_tendrilDragonELW.png";
    // Part: tendrilDragonERW
    public static final String TENDRIL_DRAGON_E_R_W_GEO = "srp:geo/misc_tendrilDragonERW.geo.json";
    public static final String TENDRIL_DRAGON_E_R_W_TEXTURE = "srp:textures/entity/misc_tendrilDragonERW.png";
    // Part: tendrilEsor
    public static final String TENDRIL_ESOR_GEO = "srp:geo/misc_tendrilEsor.geo.json";
    public static final String TENDRIL_ESOR_TEXTURE = "srp:textures/entity/misc_tendrilEsor.png";
    // Part: tendrilNogla
    public static final String TENDRIL_NOGLA_GEO = "srp:geo/misc_tendrilNogla.geo.json";
    public static final String TENDRIL_NOGLA_TEXTURE = "srp:textures/entity/misc_tendrilNogla.png";
    // Part: tendrilShyco
    public static final String TENDRIL_SHYCO_GEO = "srp:geo/misc_tendrilShyco.geo.json";
    public static final String TENDRIL_SHYCO_TEXTURE = "srp:textures/entity/misc_tendrilShyco.png";

    public TendrilEntity(EntityType<? extends PathfinderMob> type, Level level) {
        super(type, level);
    }
}
