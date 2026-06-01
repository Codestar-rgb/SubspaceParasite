package com.srp.client.model;

import com.srp.entity.InfectedInfDragonEEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfDragonEModel extends GeoModel<InfectedInfDragonEEntity> {

    // Multi-part entity — primary model: {'name': 'infDragonE', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infDragonE', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infDragonE', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infDragonE', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfDragonEEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfDragonEEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfDragonEEntity animatable) {
        return ANIMATION;
    }
}
