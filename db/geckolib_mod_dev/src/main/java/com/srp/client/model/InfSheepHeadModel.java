package com.srp.client.model;

import com.srp.entity.InfSheepHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfSheepHeadModel extends GeoModel<InfSheepHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infSheepHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infSheepHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infSheepHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfSheepHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfSheepHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfSheepHeadEntity animatable) {
        return ANIMATION;
    }
}
