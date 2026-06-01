package com.srp.client.model;

import com.srp.entity.RondEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class RondModel extends GeoModel<RondEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_rond.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_rond.png");

    @Override
    public ResourceLocation getModelResource(RondEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(RondEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(RondEntity animatable) {
        return null; // No animation file
    }
}
