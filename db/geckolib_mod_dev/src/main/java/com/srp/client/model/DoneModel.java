package com.srp.client.model;

import com.srp.entity.DoneEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DoneModel extends GeoModel<DoneEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_done.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_done.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_done.animation.json");

    @Override
    public ResourceLocation getModelResource(DoneEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DoneEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DoneEntity animatable) {
        return ANIMATION;
    }
}
