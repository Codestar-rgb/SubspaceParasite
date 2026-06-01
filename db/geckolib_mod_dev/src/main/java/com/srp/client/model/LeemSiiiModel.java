package com.srp.client.model;

import com.srp.entity.LeemSiiiEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LeemSiiiModel extends GeoModel<LeemSiiiEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_leemSIII.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_leemSIII.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_leemSIII.animation.json");

    @Override
    public ResourceLocation getModelResource(LeemSiiiEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LeemSiiiEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LeemSiiiEntity animatable) {
        return ANIMATION;
    }
}
