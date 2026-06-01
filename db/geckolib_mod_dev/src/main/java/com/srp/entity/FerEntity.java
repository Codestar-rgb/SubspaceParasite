package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class FerEntity extends Monster {

    // Part: ferBear
    public static final String FER_BEAR_GEO = "srp:geo/feral_ferBear.geo.json";
    public static final String FER_BEAR_TEXTURE = "srp:textures/entity/feral_ferBear.png";
    // Part: ferCow
    public static final String FER_COW_GEO = "srp:geo/feral_ferCow.geo.json";
    public static final String FER_COW_TEXTURE = "srp:textures/entity/feral_ferCow.png";
    // Part: ferEnderman
    public static final String FER_ENDERMAN_GEO = "srp:geo/feral_ferEnderman.geo.json";
    public static final String FER_ENDERMAN_TEXTURE = "srp:textures/entity/feral_ferEnderman.png";
    // Part: ferHorse
    public static final String FER_HORSE_GEO = "srp:geo/feral_ferHorse.geo.json";
    public static final String FER_HORSE_TEXTURE = "srp:textures/entity/feral_ferHorse.png";
    // Part: ferHuman
    public static final String FER_HUMAN_GEO = "srp:geo/feral_ferHuman.geo.json";
    public static final String FER_HUMAN_TEXTURE = "srp:textures/entity/feral_ferHuman.png";
    // Part: ferPig
    public static final String FER_PIG_GEO = "srp:geo/feral_ferPig.geo.json";
    public static final String FER_PIG_TEXTURE = "srp:textures/entity/feral_ferPig.png";
    // Part: ferSheep
    public static final String FER_SHEEP_GEO = "srp:geo/feral_ferSheep.geo.json";
    public static final String FER_SHEEP_TEXTURE = "srp:textures/entity/feral_ferSheep.png";
    // Part: ferVillager
    public static final String FER_VILLAGER_GEO = "srp:geo/feral_ferVillager.geo.json";
    public static final String FER_VILLAGER_TEXTURE = "srp:textures/entity/feral_ferVillager.png";
    // Part: ferWolf
    public static final String FER_WOLF_GEO = "srp:geo/feral_ferWolf.geo.json";
    public static final String FER_WOLF_TEXTURE = "srp:textures/entity/feral_ferWolf.png";

    public FerEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
