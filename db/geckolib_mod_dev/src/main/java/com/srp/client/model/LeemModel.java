package com.srp.client.model;

import com.srp.entity.LeemEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LeemModel extends GeoModel<LeemEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_leem.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_leem.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_leem.animation.json");

    @Override
    public ResourceLocation getModelResource(LeemEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LeemEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LeemEntity animatable) {
        return ANIMATION;
    }
}
