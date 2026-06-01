package com.srp.client.model;

import com.srp.entity.DodEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DodModel extends GeoModel<DodEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_dod.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_dod.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_dod.animation.json");

    @Override
    public ResourceLocation getModelResource(DodEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DodEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DodEntity animatable) {
        return ANIMATION;
    }
}
