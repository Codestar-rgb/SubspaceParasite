package com.srp.client.model;

import com.srp.entity.TendrilDragonErwEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilDragonErwModel extends GeoModel<TendrilDragonErwEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_tendrilDragonERW.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_tendrilDragonERW.png");

    @Override
    public ResourceLocation getModelResource(TendrilDragonErwEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilDragonErwEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilDragonErwEntity animatable) {
        return null; // No animation file
    }
}
