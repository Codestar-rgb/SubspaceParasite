package com.srp.client.model;

import com.srp.entity.GimEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class GimModel extends GeoModel<GimEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_gim.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_gim.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_gim.animation.json");

    @Override
    public ResourceLocation getModelResource(GimEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(GimEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(GimEntity animatable) {
        return ANIMATION;
    }
}
