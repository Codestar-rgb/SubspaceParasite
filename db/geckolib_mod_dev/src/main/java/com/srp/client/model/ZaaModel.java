package com.srp.client.model;

import com.srp.entity.ZaaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ZaaModel extends GeoModel<ZaaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_zaa.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_zaa.png");

    @Override
    public ResourceLocation getModelResource(ZaaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ZaaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ZaaEntity animatable) {
        return null; // No animation file
    }
}
