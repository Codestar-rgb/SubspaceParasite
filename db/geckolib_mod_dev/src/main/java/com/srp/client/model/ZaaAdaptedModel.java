package com.srp.client.model;

import com.srp.entity.ZaaAdaptedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ZaaAdaptedModel extends GeoModel<ZaaAdaptedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/adapted_zaaAdapted.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/adapted_zaaAdapted.png");

    @Override
    public ResourceLocation getModelResource(ZaaAdaptedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ZaaAdaptedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ZaaAdaptedEntity animatable) {
        return null; // No animation file
    }
}
