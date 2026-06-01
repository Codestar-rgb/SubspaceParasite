package com.srp.client.model;

import com.srp.entity.BombEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BombModel extends GeoModel<BombEntity> {

    // Multi-part entity — primary model: {'name': 'bombHost', 'has_animation': False}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_{'name': 'bombHost', 'has_animation': False}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_{'name': 'bombHost', 'has_animation': False}.png");

    @Override
    public ResourceLocation getModelResource(BombEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BombEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BombEntity animatable) {
        return null;
    }
}
