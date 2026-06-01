package com.srp.client.model;

import com.srp.entity.TendrilAngedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilAngedModel extends GeoModel<TendrilAngedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_tendrilAnged.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_tendrilAnged.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/misc_tendrilAnged.animation.json");

    @Override
    public ResourceLocation getModelResource(TendrilAngedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilAngedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilAngedEntity animatable) {
        return ANIMATION;
    }
}
