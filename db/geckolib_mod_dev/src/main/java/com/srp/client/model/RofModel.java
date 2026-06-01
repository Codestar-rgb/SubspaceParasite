package com.srp.client.model;

import com.srp.entity.RofEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class RofModel extends GeoModel<RofEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_rof.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_rof.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_rof.animation.json");

    @Override
    public ResourceLocation getModelResource(RofEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(RofEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(RofEntity animatable) {
        return ANIMATION;
    }
}
