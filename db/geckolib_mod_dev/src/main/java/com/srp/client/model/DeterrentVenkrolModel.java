package com.srp.client.model;

import com.srp.entity.DeterrentVenkrolEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DeterrentVenkrolModel extends GeoModel<DeterrentVenkrolEntity> {

    // Multi-part entity — primary model: {'name': 'venkrol', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_{'name': 'venkrol', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_{'name': 'venkrol', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_{'name': 'venkrol', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(DeterrentVenkrolEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DeterrentVenkrolEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DeterrentVenkrolEntity animatable) {
        return ANIMATION;
    }
}
