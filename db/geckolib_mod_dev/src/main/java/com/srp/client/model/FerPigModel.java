package com.srp.client.model;

import com.srp.entity.FerPigEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerPigModel extends GeoModel<FerPigEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferPig.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferPig.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferPig.animation.json");

    @Override
    public ResourceLocation getModelResource(FerPigEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerPigEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerPigEntity animatable) {
        return ANIMATION;
    }
}
