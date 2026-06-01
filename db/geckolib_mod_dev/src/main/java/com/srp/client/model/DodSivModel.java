package com.srp.client.model;

import com.srp.entity.DodSivEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DodSivModel extends GeoModel<DodSivEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_dodSIV.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_dodSIV.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_dodSIV.animation.json");

    @Override
    public ResourceLocation getModelResource(DodSivEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DodSivEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DodSivEntity animatable) {
        return ANIMATION;
    }
}
