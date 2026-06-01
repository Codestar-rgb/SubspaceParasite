package com.srp.client.model;

import com.srp.entity.InfectedInfHumanEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfHumanModel extends GeoModel<InfectedInfHumanEntity> {

    // Multi-part entity — primary model: {'name': 'infHuman', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infHuman', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infHuman', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infHuman', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfHumanEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfHumanEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfHumanEntity animatable) {
        return ANIMATION;
    }
}
