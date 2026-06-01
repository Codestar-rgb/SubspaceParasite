package com.srp.client.model;

import com.srp.entity.RanracEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class RanracModel extends GeoModel<RanracEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_ranrac.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_ranrac.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_ranrac.animation.json");

    @Override
    public ResourceLocation getModelResource(RanracEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(RanracEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(RanracEntity animatable) {
        return ANIMATION;
    }
}
