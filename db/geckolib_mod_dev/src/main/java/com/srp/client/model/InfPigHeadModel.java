package com.srp.client.model;

import com.srp.entity.InfPigHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfPigHeadModel extends GeoModel<InfPigHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infPigHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infPigHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infPigHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfPigHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfPigHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfPigHeadEntity animatable) {
        return ANIMATION;
    }
}
