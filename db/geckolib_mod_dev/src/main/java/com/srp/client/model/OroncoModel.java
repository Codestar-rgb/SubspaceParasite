package com.srp.client.model;

import com.srp.entity.OroncoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OroncoModel extends GeoModel<OroncoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/ancient_oronco.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/ancient_oronco.png");

    @Override
    public ResourceLocation getModelResource(OroncoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OroncoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OroncoEntity animatable) {
        return null; // No animation file
    }
}
