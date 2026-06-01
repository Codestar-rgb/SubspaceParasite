package com.srp.client.model;

import com.srp.entity.InfEndermanHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfEndermanHeadModel extends GeoModel<InfEndermanHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infEndermanHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infEndermanHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infEndermanHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfEndermanHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfEndermanHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfEndermanHeadEntity animatable) {
        return ANIMATION;
    }
}
