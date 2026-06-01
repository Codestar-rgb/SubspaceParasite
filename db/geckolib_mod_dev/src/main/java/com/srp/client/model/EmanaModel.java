package com.srp.client.model;

import com.srp.entity.EmanaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class EmanaModel extends GeoModel<EmanaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_emana.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_emana.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_emana.animation.json");

    @Override
    public ResourceLocation getModelResource(EmanaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(EmanaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(EmanaEntity animatable) {
        return ANIMATION;
    }
}
