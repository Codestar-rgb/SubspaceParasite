package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class InfectedInfDragonEEntity extends Monster {

    // Part: infDragonE
    public static final String INF_DRAGON_E_GEO = "srp:geo/infected_infDragonE.geo.json";
    public static final String INF_DRAGON_E_TEXTURE = "srp:textures/entity/infected_infDragonE.png";
    // Part: infDragonEHead
    public static final String INF_DRAGON_E_HEAD_GEO = "srp:geo/infected_infDragonEHead.geo.json";
    public static final String INF_DRAGON_E_HEAD_TEXTURE = "srp:textures/entity/infected_infDragonEHead.png";

    public InfectedInfDragonEEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
