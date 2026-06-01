package com.srp.client.model;

import com.srp.entity.DodSiiiEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DodSiiiModel extends GeoModel<DodSiiiEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_dodSIII.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_dodSIII.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_dodSIII.animation.json");

    @Override
    public ResourceLocation getModelResource(DodSiiiEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DodSiiiEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DodSiiiEntity animatable) {
        return ANIMATION;
    }
}
