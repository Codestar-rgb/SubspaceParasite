package com.srp.client.model;

import com.srp.entity.LeemSivEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LeemSivModel extends GeoModel<LeemSivEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_leemSIV.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_leemSIV.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_leemSIV.animation.json");

    @Override
    public ResourceLocation getModelResource(LeemSivEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LeemSivEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LeemSivEntity animatable) {
        return ANIMATION;
    }
}
