package com.srp.client.model;

import com.srp.entity.HeedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HeedModel extends GeoModel<HeedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_heed.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_heed.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_heed.animation.json");

    @Override
    public ResourceLocation getModelResource(HeedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HeedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HeedEntity animatable) {
        return ANIMATION;
    }
}
