package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class AncientOroncoEntity extends Monster {

    // Part: oronco
    public static final String ORONCO_GEO = "srp:geo/ancient_oronco.geo.json";
    public static final String ORONCO_TEXTURE = "srp:textures/entity/ancient_oronco.png";
    // Part: oroncoTen
    public static final String ORONCO_TEN_GEO = "srp:geo/ancient_oroncoTen.geo.json";
    public static final String ORONCO_TEN_TEXTURE = "srp:textures/entity/ancient_oroncoTen.png";

    public AncientOroncoEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
