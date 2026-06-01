package com.srp.client.model;

import com.srp.entity.LumEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LumModel extends GeoModel<LumEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_lum.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_lum.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_lum.animation.json");

    @Override
    public ResourceLocation getModelResource(LumEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LumEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LumEntity animatable) {
        return ANIMATION;
    }
}
