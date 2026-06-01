package com.srp.client.model;

import com.srp.entity.FlogEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FlogModel extends GeoModel<FlogEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_flog.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_flog.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_flog.animation.json");

    @Override
    public ResourceLocation getModelResource(FlogEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FlogEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FlogEntity animatable) {
        return ANIMATION;
    }
}
