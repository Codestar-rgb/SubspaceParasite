package com.srp.client.model;

import com.srp.entity.HebluEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HebluModel extends GeoModel<HebluEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/derived_heblu.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/derived_heblu.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/derived_heblu.animation.json");

    @Override
    public ResourceLocation getModelResource(HebluEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HebluEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HebluEntity animatable) {
        return ANIMATION;
    }
}
