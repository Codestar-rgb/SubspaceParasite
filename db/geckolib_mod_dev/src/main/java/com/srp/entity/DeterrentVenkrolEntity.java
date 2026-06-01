package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class DeterrentVenkrolEntity extends Monster {

    // Part: venkrol
    public static final String VENKROL_GEO = "srp:geo/deterrent_venkrol.geo.json";
    public static final String VENKROL_TEXTURE = "srp:textures/entity/deterrent_venkrol.png";
    // Part: venkrolSII
    public static final String VENKROL_S_I_I_GEO = "srp:geo/deterrent_venkrolSII.geo.json";
    public static final String VENKROL_S_I_I_TEXTURE = "srp:textures/entity/deterrent_venkrolSII.png";
    // Part: venkrolSIII
    public static final String VENKROL_S_I_I_I_GEO = "srp:geo/deterrent_venkrolSIII.geo.json";
    public static final String VENKROL_S_I_I_I_TEXTURE = "srp:textures/entity/deterrent_venkrolSIII.png";
    // Part: venkrolSIV
    public static final String VENKROL_S_I_V_GEO = "srp:geo/deterrent_venkrolSIV.geo.json";
    public static final String VENKROL_S_I_V_TEXTURE = "srp:textures/entity/deterrent_venkrolSIV.png";
    // Part: venkrolSV
    public static final String VENKROL_S_V_GEO = "srp:geo/deterrent_venkrolSV.geo.json";
    public static final String VENKROL_S_V_TEXTURE = "srp:textures/entity/deterrent_venkrolSV.png";

    public DeterrentVenkrolEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
