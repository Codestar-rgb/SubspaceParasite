package com.srp.client.model;

import com.srp.entity.TendrilEsorEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilEsorModel extends GeoModel<TendrilEsorEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_tendrilEsor.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_tendrilEsor.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/misc_tendrilEsor.animation.json");

    @Override
    public ResourceLocation getModelResource(TendrilEsorEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilEsorEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilEsorEntity animatable) {
        return ANIMATION;
    }
}
