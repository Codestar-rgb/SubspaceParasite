package com.srp.client.model;

import com.srp.entity.InfHorseHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfHorseHeadModel extends GeoModel<InfHorseHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infHorseHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infHorseHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infHorseHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfHorseHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfHorseHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfHorseHeadEntity animatable) {
        return ANIMATION;
    }
}
