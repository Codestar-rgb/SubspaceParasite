package com.srp.client.model;

import com.srp.entity.FerHorseEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerHorseModel extends GeoModel<FerHorseEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferHorse.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferHorse.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferHorse.animation.json");

    @Override
    public ResourceLocation getModelResource(FerHorseEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerHorseEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerHorseEntity animatable) {
        return ANIMATION;
    }
}
