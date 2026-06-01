package com.srp.client.model;

import com.srp.entity.InfHumanHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfHumanHeadModel extends GeoModel<InfHumanHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infHumanHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infHumanHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infHumanHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfHumanHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfHumanHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfHumanHeadEntity animatable) {
        return ANIMATION;
    }
}
