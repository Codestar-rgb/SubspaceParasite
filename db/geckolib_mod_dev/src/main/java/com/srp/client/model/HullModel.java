package com.srp.client.model;

import com.srp.entity.HullEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HullModel extends GeoModel<HullEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_hull.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_hull.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_hull.animation.json");

    @Override
    public ResourceLocation getModelResource(HullEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HullEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HullEntity animatable) {
        return ANIMATION;
    }
}
