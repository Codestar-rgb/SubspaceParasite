package com.srp.client.model;

import com.srp.entity.SpeEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class SpeModel extends GeoModel<SpeEntity> {

    // Multi-part entity — primary model: {'name': 'speBear', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'speBear', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'speBear', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'speBear', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(SpeEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(SpeEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(SpeEntity animatable) {
        return ANIMATION;
    }
}
