package com.srp.client.model;

import com.srp.entity.HullAdaptedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HullAdaptedModel extends GeoModel<HullAdaptedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/adapted_hullAdapted.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/adapted_hullAdapted.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/adapted_hullAdapted.animation.json");

    @Override
    public ResourceLocation getModelResource(HullAdaptedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HullAdaptedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HullAdaptedEntity animatable) {
        return ANIMATION;
    }
}
