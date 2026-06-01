package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class DeterrentDodEntity extends Monster {

    // Part: dod
    public static final String DOD_GEO = "srp:geo/deterrent_dod.geo.json";
    public static final String DOD_TEXTURE = "srp:textures/entity/deterrent_dod.png";
    // Part: dodSII
    public static final String DOD_S_I_I_GEO = "srp:geo/deterrent_dodSII.geo.json";
    public static final String DOD_S_I_I_TEXTURE = "srp:textures/entity/deterrent_dodSII.png";
    // Part: dodSIII
    public static final String DOD_S_I_I_I_GEO = "srp:geo/deterrent_dodSIII.geo.json";
    public static final String DOD_S_I_I_I_TEXTURE = "srp:textures/entity/deterrent_dodSIII.png";
    // Part: dodSIV
    public static final String DOD_S_I_V_GEO = "srp:geo/deterrent_dodSIV.geo.json";
    public static final String DOD_S_I_V_TEXTURE = "srp:textures/entity/deterrent_dodSIV.png";
    // Part: dodSIVH
    public static final String DOD_S_I_V_H_GEO = "srp:geo/deterrent_dodSIVH.geo.json";
    public static final String DOD_S_I_V_H_TEXTURE = "srp:textures/entity/deterrent_dodSIVH.png";
    // Part: dodT
    public static final String DOD_T_GEO = "srp:geo/deterrent_dodT.geo.json";
    public static final String DOD_T_TEXTURE = "srp:textures/entity/deterrent_dodT.png";

    public DeterrentDodEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
