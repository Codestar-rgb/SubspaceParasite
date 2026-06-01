package com.srp.client.model;

import com.srp.entity.TendrilShycoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilShycoModel extends GeoModel<TendrilShycoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_tendrilShyco.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_tendrilShyco.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/misc_tendrilShyco.animation.json");

    @Override
    public ResourceLocation getModelResource(TendrilShycoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilShycoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilShycoEntity animatable) {
        return ANIMATION;
    }
}
