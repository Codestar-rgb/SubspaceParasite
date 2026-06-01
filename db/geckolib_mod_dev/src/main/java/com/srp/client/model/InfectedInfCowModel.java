package com.srp.client.model;

import com.srp.entity.InfectedInfCowEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfCowModel extends GeoModel<InfectedInfCowEntity> {

    // Multi-part entity — primary model: {'name': 'infCow', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infCow', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infCow', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infCow', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfCowEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfCowEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfCowEntity animatable) {
        return ANIMATION;
    }
}
