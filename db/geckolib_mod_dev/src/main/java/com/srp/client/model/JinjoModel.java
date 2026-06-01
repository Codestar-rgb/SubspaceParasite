package com.srp.client.model;

import com.srp.entity.JinjoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class JinjoModel extends GeoModel<JinjoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_jinjo.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_jinjo.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_jinjo.animation.json");

    @Override
    public ResourceLocation getModelResource(JinjoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(JinjoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(JinjoEntity animatable) {
        return ANIMATION;
    }
}
