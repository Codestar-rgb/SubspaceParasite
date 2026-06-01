package com.srp.client.model;

import com.srp.entity.OroncoTenEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OroncoTenModel extends GeoModel<OroncoTenEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/ancient_oroncoTen.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/ancient_oroncoTen.png");

    @Override
    public ResourceLocation getModelResource(OroncoTenEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OroncoTenEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OroncoTenEntity animatable) {
        return null; // No animation file
    }
}
