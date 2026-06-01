package com.srp.client.model;

import com.srp.entity.FlamEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FlamModel extends GeoModel<FlamEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_flam.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_flam.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_flam.animation.json");

    @Override
    public ResourceLocation getModelResource(FlamEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FlamEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FlamEntity animatable) {
        return ANIMATION;
    }
}
