package com.srp.client.model;

import com.srp.entity.InfEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfModel extends GeoModel<InfEntity> {

    // Multi-part entity — primary model: {'name': 'infBear', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infBear', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infBear', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infBear', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfEntity animatable) {
        return ANIMATION;
    }
}
