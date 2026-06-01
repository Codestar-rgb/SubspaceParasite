package com.srp.client.model;

import com.srp.entity.PheonEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class PheonModel extends GeoModel<PheonEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_pheon.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_pheon.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_pheon.animation.json");

    @Override
    public ResourceLocation getModelResource(PheonEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(PheonEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(PheonEntity animatable) {
        return ANIMATION;
    }
}
