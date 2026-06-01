package com.srp.client.model;

import com.srp.entity.BiomassEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BiomassModel extends GeoModel<BiomassEntity> {

    // Multi-part entity — primary model: {'name': 'biomassPod', 'has_animation': False}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_{'name': 'biomassPod', 'has_animation': False}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_{'name': 'biomassPod', 'has_animation': False}.png");

    @Override
    public ResourceLocation getModelResource(BiomassEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BiomassEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BiomassEntity animatable) {
        return null;
    }
}
