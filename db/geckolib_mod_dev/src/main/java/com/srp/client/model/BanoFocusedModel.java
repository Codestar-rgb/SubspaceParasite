package com.srp.client.model;

import com.srp.entity.BanoFocusedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BanoFocusedModel extends GeoModel<BanoFocusedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/focused_banoFocused.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/focused_banoFocused.png");

    @Override
    public ResourceLocation getModelResource(BanoFocusedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BanoFocusedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BanoFocusedEntity animatable) {
        return null; // No animation file
    }
}
