package com.srp.client.model;

import com.srp.entity.InfHorseEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfHorseModel extends GeoModel<InfHorseEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infHorse.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infHorse.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infHorse.animation.json");

    @Override
    public ResourceLocation getModelResource(InfHorseEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfHorseEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfHorseEntity animatable) {
        return ANIMATION;
    }
}
