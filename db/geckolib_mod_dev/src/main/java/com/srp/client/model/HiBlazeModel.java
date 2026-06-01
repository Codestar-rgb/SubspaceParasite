package com.srp.client.model;

import com.srp.entity.HiBlazeEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HiBlazeModel extends GeoModel<HiBlazeEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/hijacked_hiBlaze.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/hijacked_hiBlaze.png");

    @Override
    public ResourceLocation getModelResource(HiBlazeEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HiBlazeEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HiBlazeEntity animatable) {
        return null; // No animation file
    }
}
