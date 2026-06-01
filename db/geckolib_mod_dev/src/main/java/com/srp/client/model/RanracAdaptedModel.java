package com.srp.client.model;

import com.srp.entity.RanracAdaptedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class RanracAdaptedModel extends GeoModel<RanracAdaptedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/adapted_ranracAdapted.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/adapted_ranracAdapted.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/adapted_ranracAdapted.animation.json");

    @Override
    public ResourceLocation getModelResource(RanracAdaptedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(RanracAdaptedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(RanracAdaptedEntity animatable) {
        return ANIMATION;
    }
}
