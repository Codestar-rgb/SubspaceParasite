package com.srp.client.model;

import com.srp.entity.WymoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class WymoModel extends GeoModel<WymoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_wymo.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_wymo.png");

    @Override
    public ResourceLocation getModelResource(WymoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(WymoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(WymoEntity animatable) {
        return null; // No animation file
    }
}
