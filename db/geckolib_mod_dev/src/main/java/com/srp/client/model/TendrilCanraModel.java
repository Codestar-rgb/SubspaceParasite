package com.srp.client.model;

import com.srp.entity.TendrilCanraEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilCanraModel extends GeoModel<TendrilCanraEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_tendrilCanra.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_tendrilCanra.png");

    @Override
    public ResourceLocation getModelResource(TendrilCanraEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilCanraEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilCanraEntity animatable) {
        return null; // No animation file
    }
}
