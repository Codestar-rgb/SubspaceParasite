package com.srp.client.model;

import com.srp.entity.TendrilEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilModel extends GeoModel<TendrilEntity> {

    // Multi-part entity — primary model: {'name': 'tendrilAnged', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_{'name': 'tendrilAnged', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_{'name': 'tendrilAnged', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/misc_{'name': 'tendrilAnged', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(TendrilEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilEntity animatable) {
        return ANIMATION;
    }
}
