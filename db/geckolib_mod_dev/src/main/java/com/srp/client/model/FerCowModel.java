package com.srp.client.model;

import com.srp.entity.FerCowEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerCowModel extends GeoModel<FerCowEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferCow.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferCow.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferCow.animation.json");

    @Override
    public ResourceLocation getModelResource(FerCowEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerCowEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerCowEntity animatable) {
        return ANIMATION;
    }
}
