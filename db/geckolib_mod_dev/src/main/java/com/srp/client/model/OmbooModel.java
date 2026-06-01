package com.srp.client.model;

import com.srp.entity.OmbooEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OmbooModel extends GeoModel<OmbooEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_omboo.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_omboo.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_omboo.animation.json");

    @Override
    public ResourceLocation getModelResource(OmbooEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OmbooEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OmbooEntity animatable) {
        return ANIMATION;
    }
}
