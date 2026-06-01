package com.srp.client.model;

import com.srp.entity.ButholEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ButholModel extends GeoModel<ButholEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_buthol.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_buthol.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_buthol.animation.json");

    @Override
    public ResourceLocation getModelResource(ButholEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ButholEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ButholEntity animatable) {
        return ANIMATION;
    }
}
