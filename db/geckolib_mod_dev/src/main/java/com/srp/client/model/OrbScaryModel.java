package com.srp.client.model;

import com.srp.entity.OrbScaryEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OrbScaryModel extends GeoModel<OrbScaryEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_orbScary.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_orbScary.png");

    @Override
    public ResourceLocation getModelResource(OrbScaryEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OrbScaryEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OrbScaryEntity animatable) {
        return null; // No animation file
    }
}
