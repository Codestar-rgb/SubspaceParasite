package com.srp.client.model;

import com.srp.entity.AncientOroncoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class AncientOroncoModel extends GeoModel<AncientOroncoEntity> {

    // Multi-part entity — primary model: {'name': 'oronco', 'has_animation': False}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/ancient_{'name': 'oronco', 'has_animation': False}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/ancient_{'name': 'oronco', 'has_animation': False}.png");

    @Override
    public ResourceLocation getModelResource(AncientOroncoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AncientOroncoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AncientOroncoEntity animatable) {
        return null;
    }
}
