package com.srp.client.model;

import com.srp.entity.TendrilDragonElwEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilDragonElwModel extends GeoModel<TendrilDragonElwEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_tendrilDragonELW.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_tendrilDragonELW.png");

    @Override
    public ResourceLocation getModelResource(TendrilDragonElwEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilDragonElwEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilDragonElwEntity animatable) {
        return null; // No animation file
    }
}
