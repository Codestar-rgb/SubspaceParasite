package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class AboEntity extends Monster {

    // Part: aboBodies
    public static final String ABO_BODIES_GEO = "srp:geo/abomination_aboBodies.geo.json";
    public static final String ABO_BODIES_TEXTURE = "srp:textures/entity/abomination_aboBodies.png";
    // Part: aboHead
    public static final String ABO_HEAD_GEO = "srp:geo/abomination_aboHead.geo.json";
    public static final String ABO_HEAD_TEXTURE = "srp:textures/entity/abomination_aboHead.png";

    public AboEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
