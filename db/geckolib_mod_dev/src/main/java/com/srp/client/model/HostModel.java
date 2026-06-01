package com.srp.client.model;

import com.srp.entity.HostEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HostModel extends GeoModel<HostEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_host.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_host.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_host.animation.json");

    @Override
    public ResourceLocation getModelResource(HostEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HostEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HostEntity animatable) {
        return ANIMATION;
    }
}
