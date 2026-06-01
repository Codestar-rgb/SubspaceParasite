package com.srp.client.model;

import com.srp.entity.FerEndermanEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerEndermanModel extends GeoModel<FerEndermanEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferEnderman.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferEnderman.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferEnderman.animation.json");

    @Override
    public ResourceLocation getModelResource(FerEndermanEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerEndermanEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerEndermanEntity animatable) {
        return ANIMATION;
    }
}
