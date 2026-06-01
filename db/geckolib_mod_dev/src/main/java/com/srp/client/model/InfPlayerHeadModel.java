package com.srp.client.model;

import com.srp.entity.InfPlayerHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfPlayerHeadModel extends GeoModel<InfPlayerHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infPlayerHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infPlayerHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infPlayerHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfPlayerHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfPlayerHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfPlayerHeadEntity animatable) {
        return ANIMATION;
    }
}
