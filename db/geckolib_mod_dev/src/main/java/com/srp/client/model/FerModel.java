package com.srp.client.model;

import com.srp.entity.FerEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerModel extends GeoModel<FerEntity> {

    // Multi-part entity — primary model: {'name': 'ferBear', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_{'name': 'ferBear', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_{'name': 'ferBear', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_{'name': 'ferBear', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(FerEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerEntity animatable) {
        return ANIMATION;
    }
}
