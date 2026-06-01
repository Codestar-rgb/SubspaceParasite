package com.srp.client.model;

import com.srp.entity.InfectedInfEndermanEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfEndermanModel extends GeoModel<InfectedInfEndermanEntity> {

    // Multi-part entity — primary model: {'name': 'infEnderman', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infEnderman', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infEnderman', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infEnderman', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfEndermanEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfEndermanEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfEndermanEntity animatable) {
        return ANIMATION;
    }
}
