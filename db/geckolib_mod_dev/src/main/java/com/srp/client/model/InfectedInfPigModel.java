package com.srp.client.model;

import com.srp.entity.InfectedInfPigEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfPigModel extends GeoModel<InfectedInfPigEntity> {

    // Multi-part entity — primary model: {'name': 'infPig', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infPig', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infPig', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infPig', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfPigEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfPigEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfPigEntity animatable) {
        return ANIMATION;
    }
}
