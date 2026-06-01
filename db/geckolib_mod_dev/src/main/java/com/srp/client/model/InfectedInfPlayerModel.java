package com.srp.client.model;

import com.srp.entity.InfectedInfPlayerEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfPlayerModel extends GeoModel<InfectedInfPlayerEntity> {

    // Multi-part entity — primary model: {'name': 'infPlayer', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infPlayer', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infPlayer', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infPlayer', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfPlayerEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfPlayerEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfPlayerEntity animatable) {
        return ANIMATION;
    }
}
