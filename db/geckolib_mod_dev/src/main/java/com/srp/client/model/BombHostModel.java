package com.srp.client.model;

import com.srp.entity.BombHostEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BombHostModel extends GeoModel<BombHostEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_bombHost.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_bombHost.png");

    @Override
    public ResourceLocation getModelResource(BombHostEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BombHostEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BombHostEntity animatable) {
        return null; // No animation file
    }
}
