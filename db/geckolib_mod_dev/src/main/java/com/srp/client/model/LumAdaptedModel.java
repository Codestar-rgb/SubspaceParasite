package com.srp.client.model;

import com.srp.entity.LumAdaptedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LumAdaptedModel extends GeoModel<LumAdaptedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/adapted_lumAdapted.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/adapted_lumAdapted.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/adapted_lumAdapted.animation.json");

    @Override
    public ResourceLocation getModelResource(LumAdaptedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LumAdaptedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LumAdaptedEntity animatable) {
        return ANIMATION;
    }
}
