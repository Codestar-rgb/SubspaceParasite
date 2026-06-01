package com.srp.client.model;

import com.srp.entity.NadeEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class NadeModel extends GeoModel<NadeEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_nade.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_nade.png");

    @Override
    public ResourceLocation getModelResource(NadeEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(NadeEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(NadeEntity animatable) {
        return null; // No animation file
    }
}
