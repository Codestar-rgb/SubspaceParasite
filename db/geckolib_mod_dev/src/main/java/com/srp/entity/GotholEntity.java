package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class GotholEntity extends Monster {

    public GotholEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
