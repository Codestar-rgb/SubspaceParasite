package com.srp.entity;

import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class BombHostEntity extends PathfinderMob {

    public BombHostEntity(EntityType<? extends PathfinderMob> type, Level level) {
        super(type, level);
    }
}
