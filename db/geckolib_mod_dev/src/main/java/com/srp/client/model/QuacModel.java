package com.srp.client.model;

import com.srp.entity.QuacEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class QuacModel extends GeoModel<QuacEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_quac.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_quac.png");

    @Override
    public ResourceLocation getModelResource(QuacEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(QuacEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(QuacEntity animatable) {
        return null; // No animation file
    }
}
