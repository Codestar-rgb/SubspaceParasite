package com.srp.entity;

import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class MeteorEntity extends PathfinderMob {

    public MeteorEntity(EntityType<? extends PathfinderMob> type, Level level) {
        super(type, level);
    }
}
