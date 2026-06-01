package com.srp.client.model;

import com.srp.entity.OroncoAwEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OroncoAwModel extends GeoModel<OroncoAwEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/awakened_oroncoAW.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/awakened_oroncoAW.png");

    @Override
    public ResourceLocation getModelResource(OroncoAwEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OroncoAwEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OroncoAwEntity animatable) {
        return null; // No animation file
    }
}
