package com.srp.client.model;

import com.srp.entity.LodoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LodoModel extends GeoModel<LodoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_lodo.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_lodo.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_lodo.animation.json");

    @Override
    public ResourceLocation getModelResource(LodoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LodoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LodoEntity animatable) {
        return ANIMATION;
    }
}
