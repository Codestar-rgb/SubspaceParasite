package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class DeterrentLeemEntity extends Monster {

    // Part: leem
    public static final String LEEM_GEO = "srp:geo/deterrent_leem.geo.json";
    public static final String LEEM_TEXTURE = "srp:textures/entity/deterrent_leem.png";
    // Part: leemB
    public static final String LEEM_B_GEO = "srp:geo/deterrent_leemB.geo.json";
    public static final String LEEM_B_TEXTURE = "srp:textures/entity/deterrent_leemB.png";
    // Part: leemSII
    public static final String LEEM_S_I_I_GEO = "srp:geo/deterrent_leemSII.geo.json";
    public static final String LEEM_S_I_I_TEXTURE = "srp:textures/entity/deterrent_leemSII.png";
    // Part: leemSIII
    public static final String LEEM_S_I_I_I_GEO = "srp:geo/deterrent_leemSIII.geo.json";
    public static final String LEEM_S_I_I_I_TEXTURE = "srp:textures/entity/deterrent_leemSIII.png";
    // Part: leemSIV
    public static final String LEEM_S_I_V_GEO = "srp:geo/deterrent_leemSIV.geo.json";
    public static final String LEEM_S_I_V_TEXTURE = "srp:textures/entity/deterrent_leemSIV.png";

    public DeterrentLeemEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
