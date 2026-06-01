package com.srp.client.model;

import com.srp.entity.LeshEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LeshModel extends GeoModel<LeshEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_lesh.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_lesh.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_lesh.animation.json");

    @Override
    public ResourceLocation getModelResource(LeshEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LeshEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LeshEntity animatable) {
        return ANIMATION;
    }
}
