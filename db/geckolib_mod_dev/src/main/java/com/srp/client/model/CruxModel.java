package com.srp.client.model;

import com.srp.entity.CruxEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class CruxModel extends GeoModel<CruxEntity> {

    // Multi-part entity — primary model: {'name': 'cruxA', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_{'name': 'cruxA', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_{'name': 'cruxA', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_{'name': 'cruxA', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(CruxEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(CruxEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(CruxEntity animatable) {
        return ANIMATION;
    }
}
