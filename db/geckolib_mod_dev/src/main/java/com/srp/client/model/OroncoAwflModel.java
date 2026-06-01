package com.srp.client.model;

import com.srp.entity.OroncoAwflEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OroncoAwflModel extends GeoModel<OroncoAwflEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/awakened_oroncoAWFL.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/awakened_oroncoAWFL.png");

    @Override
    public ResourceLocation getModelResource(OroncoAwflEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OroncoAwflEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OroncoAwflEntity animatable) {
        return null; // No animation file
    }
}
