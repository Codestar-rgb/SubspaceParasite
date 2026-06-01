package com.srp.client.model;

import com.srp.entity.WymoAdaptedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class WymoAdaptedModel extends GeoModel<WymoAdaptedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/adapted_wymoAdapted.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/adapted_wymoAdapted.png");

    @Override
    public ResourceLocation getModelResource(WymoAdaptedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(WymoAdaptedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(WymoAdaptedEntity animatable) {
        return null; // No animation file
    }
}
