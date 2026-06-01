package com.srp.client.model;

import com.srp.entity.HostIiEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HostIiModel extends GeoModel<HostIiEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_hostII.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_hostII.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_hostII.animation.json");

    @Override
    public ResourceLocation getModelResource(HostIiEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HostIiEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HostIiEntity animatable) {
        return ANIMATION;
    }
}
