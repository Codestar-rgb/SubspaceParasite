package com.srp.client.model;

import com.srp.entity.OrbVoidEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OrbVoidModel extends GeoModel<OrbVoidEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_orbVoid.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_orbVoid.png");

    @Override
    public ResourceLocation getModelResource(OrbVoidEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OrbVoidEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OrbVoidEntity animatable) {
        return null; // No animation file
    }
}
