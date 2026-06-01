package com.srp.client.model;

import com.srp.entity.InfectedInfWolfEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfWolfModel extends GeoModel<InfectedInfWolfEntity> {

    // Multi-part entity — primary model: {'name': 'infWolf', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infWolf', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infWolf', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infWolf', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfWolfEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfWolfEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfWolfEntity animatable) {
        return ANIMATION;
    }
}
