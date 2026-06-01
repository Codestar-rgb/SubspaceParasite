package com.srp.client.model;

import com.srp.entity.InfectedInfHorseEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfHorseModel extends GeoModel<InfectedInfHorseEntity> {

    // Multi-part entity — primary model: {'name': 'infHorse', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infHorse', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infHorse', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infHorse', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfHorseEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfHorseEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfHorseEntity animatable) {
        return ANIMATION;
    }
}
