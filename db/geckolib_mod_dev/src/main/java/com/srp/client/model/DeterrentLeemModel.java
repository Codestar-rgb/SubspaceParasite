package com.srp.client.model;

import com.srp.entity.DeterrentLeemEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DeterrentLeemModel extends GeoModel<DeterrentLeemEntity> {

    // Multi-part entity — primary model: {'name': 'leem', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_{'name': 'leem', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_{'name': 'leem', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_{'name': 'leem', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(DeterrentLeemEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DeterrentLeemEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DeterrentLeemEntity animatable) {
        return ANIMATION;
    }
}
