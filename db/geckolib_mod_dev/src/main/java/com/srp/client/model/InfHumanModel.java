package com.srp.client.model;

import com.srp.entity.InfHumanEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfHumanModel extends GeoModel<InfHumanEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infHuman.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infHuman.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infHuman.animation.json");

    @Override
    public ResourceLocation getModelResource(InfHumanEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfHumanEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfHumanEntity animatable) {
        return ANIMATION;
    }
}
