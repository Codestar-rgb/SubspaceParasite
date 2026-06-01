package com.srp.client.model;

import com.srp.entity.DodSivhEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DodSivhModel extends GeoModel<DodSivhEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_dodSIVH.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_dodSIVH.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_dodSIVH.animation.json");

    @Override
    public ResourceLocation getModelResource(DodSivhEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DodSivhEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DodSivhEntity animatable) {
        return ANIMATION;
    }
}
