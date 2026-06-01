package com.srp.client.model;

import com.srp.entity.EmanaAdaptedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class EmanaAdaptedModel extends GeoModel<EmanaAdaptedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/adapted_emanaAdapted.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/adapted_emanaAdapted.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/adapted_emanaAdapted.animation.json");

    @Override
    public ResourceLocation getModelResource(EmanaAdaptedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(EmanaAdaptedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(EmanaAdaptedEntity animatable) {
        return ANIMATION;
    }
}
