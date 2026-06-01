package com.srp.client.model;

import com.srp.entity.InfEndermanEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfEndermanModel extends GeoModel<InfEndermanEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infEnderman.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infEnderman.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infEnderman.animation.json");

    @Override
    public ResourceLocation getModelResource(InfEndermanEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfEndermanEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfEndermanEntity animatable) {
        return ANIMATION;
    }
}
