package com.srp.entity;

import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;

public class GanroEntity extends Monster {

    public GanroEntity(EntityType<? extends Monster> type, Level level) {
        super(type, level);
    }
}
