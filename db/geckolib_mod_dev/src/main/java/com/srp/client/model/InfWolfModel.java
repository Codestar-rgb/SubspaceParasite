package com.srp.client.model;

import com.srp.entity.InfWolfEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfWolfModel extends GeoModel<InfWolfEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infWolf.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infWolf.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infWolf.animation.json");

    @Override
    public ResourceLocation getModelResource(InfWolfEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfWolfEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfWolfEntity animatable) {
        return ANIMATION;
    }
}
