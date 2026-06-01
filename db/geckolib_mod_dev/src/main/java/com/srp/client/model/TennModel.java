package com.srp.client.model;

import com.srp.entity.TennEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TennModel extends GeoModel<TennEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_tenn.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_tenn.png");

    @Override
    public ResourceLocation getModelResource(TennEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TennEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TennEntity animatable) {
        return null; // No animation file
    }
}
