package com.srp.client.model;

import com.srp.entity.OrbEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OrbModel extends GeoModel<OrbEntity> {

    // Multi-part entity — primary model: {'name': 'orbScary', 'has_animation': False}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_{'name': 'orbScary', 'has_animation': False}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_{'name': 'orbScary', 'has_animation': False}.png");

    @Override
    public ResourceLocation getModelResource(OrbEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OrbEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OrbEntity animatable) {
        return null;
    }
}
