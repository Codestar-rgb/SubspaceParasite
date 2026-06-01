package com.srp.client.model;

import com.srp.entity.AboEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class AboModel extends GeoModel<AboEntity> {

    // Multi-part entity — primary model: {'name': 'aboBodies', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/abomination_{'name': 'aboBodies', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/abomination_{'name': 'aboBodies', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/abomination_{'name': 'aboBodies', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(AboEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AboEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AboEntity animatable) {
        return ANIMATION;
    }
}
