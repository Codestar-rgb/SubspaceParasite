package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class DorpaEntity extends Monster {

    public DorpaEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
