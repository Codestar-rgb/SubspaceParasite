package com.srp.client.model;

import com.srp.entity.BanoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BanoModel extends GeoModel<BanoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_bano.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_bano.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_bano.animation.json");

    @Override
    public ResourceLocation getModelResource(BanoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BanoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BanoEntity animatable) {
        return ANIMATION;
    }
}
