package com.srp.client.model;

import com.srp.entity.ShycoFocusedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ShycoFocusedModel extends GeoModel<ShycoFocusedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/focused_shycoFocused.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/focused_shycoFocused.png");

    @Override
    public ResourceLocation getModelResource(ShycoFocusedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ShycoFocusedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ShycoFocusedEntity animatable) {
        return null; // No animation file
    }
}
