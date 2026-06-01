package com.srp.client.model;

import com.srp.entity.FerHumanEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerHumanModel extends GeoModel<FerHumanEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferHuman.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferHuman.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferHuman.animation.json");

    @Override
    public ResourceLocation getModelResource(FerHumanEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerHumanEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerHumanEntity animatable) {
        return ANIMATION;
    }
}
