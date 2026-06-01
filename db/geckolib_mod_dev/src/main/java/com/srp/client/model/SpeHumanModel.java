package com.srp.client.model;

import com.srp.entity.SpeHumanEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class SpeHumanModel extends GeoModel<SpeHumanEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_speHuman.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_speHuman.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_speHuman.animation.json");

    @Override
    public ResourceLocation getModelResource(SpeHumanEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(SpeHumanEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(SpeHumanEntity animatable) {
        return ANIMATION;
    }
}
