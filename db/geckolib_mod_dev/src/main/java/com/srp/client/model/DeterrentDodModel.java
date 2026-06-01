package com.srp.client.model;

import com.srp.entity.DeterrentDodEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DeterrentDodModel extends GeoModel<DeterrentDodEntity> {

    // Multi-part entity — primary model: {'name': 'dod', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_{'name': 'dod', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_{'name': 'dod', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_{'name': 'dod', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(DeterrentDodEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DeterrentDodEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DeterrentDodEntity animatable) {
        return ANIMATION;
    }
}
