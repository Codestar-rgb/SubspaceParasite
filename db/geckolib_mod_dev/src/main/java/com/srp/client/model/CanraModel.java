package com.srp.client.model;

import com.srp.entity.CanraEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class CanraModel extends GeoModel<CanraEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_canra.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_canra.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_canra.animation.json");

    @Override
    public ResourceLocation getModelResource(CanraEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(CanraEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(CanraEntity animatable) {
        return ANIMATION;
    }
}
