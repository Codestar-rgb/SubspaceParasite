package com.srp.client.model;

import com.srp.entity.GoreEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class GoreModel extends GeoModel<GoreEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_gore.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_gore.png");

    @Override
    public ResourceLocation getModelResource(GoreEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(GoreEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(GoreEntity animatable) {
        return null; // No animation file
    }
}
