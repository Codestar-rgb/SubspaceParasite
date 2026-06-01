package com.srp.client.model;

import com.srp.entity.InfCowHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfCowHeadModel extends GeoModel<InfCowHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infCowHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infCowHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infCowHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfCowHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfCowHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfCowHeadEntity animatable) {
        return ANIMATION;
    }
}
