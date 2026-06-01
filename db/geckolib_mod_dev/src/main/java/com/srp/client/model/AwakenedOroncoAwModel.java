package com.srp.client.model;

import com.srp.entity.AwakenedOroncoAwEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class AwakenedOroncoAwModel extends GeoModel<AwakenedOroncoAwEntity> {

    // Multi-part entity — primary model: {'name': 'oroncoAW', 'has_animation': False}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/awakened_{'name': 'oroncoAW', 'has_animation': False}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/awakened_{'name': 'oroncoAW', 'has_animation': False}.png");

    @Override
    public ResourceLocation getModelResource(AwakenedOroncoAwEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AwakenedOroncoAwEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AwakenedOroncoAwEntity animatable) {
        return null;
    }
}
