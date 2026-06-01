package com.srp.client.model;

import com.srp.entity.InfWolfHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfWolfHeadModel extends GeoModel<InfWolfHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infWolfHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infWolfHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infWolfHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfWolfHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfWolfHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfWolfHeadEntity animatable) {
        return ANIMATION;
    }
}
