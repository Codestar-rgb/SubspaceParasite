package com.srp.client.model;

import com.srp.entity.FerWolfEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerWolfModel extends GeoModel<FerWolfEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferWolf.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferWolf.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferWolf.animation.json");

    @Override
    public ResourceLocation getModelResource(FerWolfEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerWolfEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerWolfEntity animatable) {
        return ANIMATION;
    }
}
