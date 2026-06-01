package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InhooEntity extends Monster {

    // Part: inhooM
    public static final String INHOO_M_GEO = "srp:geo/crude_inhooM.geo.json";
    public static final String INHOO_M_TEXTURE = "srp:textures/entity/crude_inhooM.png";
    // Part: inhooS
    public static final String INHOO_S_GEO = "srp:geo/crude_inhooS.geo.json";
    public static final String INHOO_S_TEXTURE = "srp:textures/entity/crude_inhooS.png";

    public InhooEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
