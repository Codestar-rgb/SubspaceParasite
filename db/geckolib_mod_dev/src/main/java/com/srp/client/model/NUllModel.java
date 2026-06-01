package com.srp.client.model;

import com.srp.entity.NUllEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class NUllModel extends GeoModel<NUllEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_nULL.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_nULL.png");

    @Override
    public ResourceLocation getModelResource(NUllEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(NUllEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(NUllEntity animatable) {
        return null; // No animation file
    }
}
