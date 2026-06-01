package com.srp.client.model;

import com.srp.entity.InfPigEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfPigModel extends GeoModel<InfPigEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infPig.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infPig.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infPig.animation.json");

    @Override
    public ResourceLocation getModelResource(InfPigEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfPigEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfPigEntity animatable) {
        return ANIMATION;
    }
}
