package com.srp.client.model;

import com.srp.entity.FerBearEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerBearModel extends GeoModel<FerBearEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferBear.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferBear.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferBear.animation.json");

    @Override
    public ResourceLocation getModelResource(FerBearEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerBearEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerBearEntity animatable) {
        return ANIMATION;
    }
}
