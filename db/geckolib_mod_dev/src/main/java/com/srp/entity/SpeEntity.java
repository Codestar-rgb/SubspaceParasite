package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class SpeEntity extends Monster {

    // Part: speBear
    public static final String SPE_BEAR_GEO = "srp:geo/infected_speBear.geo.json";
    public static final String SPE_BEAR_TEXTURE = "srp:textures/entity/infected_speBear.png";
    // Part: speCow
    public static final String SPE_COW_GEO = "srp:geo/infected_speCow.geo.json";
    public static final String SPE_COW_TEXTURE = "srp:textures/entity/infected_speCow.png";
    // Part: speEnderman
    public static final String SPE_ENDERMAN_GEO = "srp:geo/infected_speEnderman.geo.json";
    public static final String SPE_ENDERMAN_TEXTURE = "srp:textures/entity/infected_speEnderman.png";
    // Part: speHuman
    public static final String SPE_HUMAN_GEO = "srp:geo/infected_speHuman.geo.json";
    public static final String SPE_HUMAN_TEXTURE = "srp:textures/entity/infected_speHuman.png";
    // Part: speSheep
    public static final String SPE_SHEEP_GEO = "srp:geo/infected_speSheep.geo.json";
    public static final String SPE_SHEEP_TEXTURE = "srp:textures/entity/infected_speSheep.png";
    // Part: speVillager
    public static final String SPE_VILLAGER_GEO = "srp:geo/infected_speVillager.geo.json";
    public static final String SPE_VILLAGER_TEXTURE = "srp:textures/entity/infected_speVillager.png";

    public SpeEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
