package com.srp.client.model;

import com.srp.entity.DorpaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DorpaModel extends GeoModel<DorpaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_dorpa.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_dorpa.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_dorpa.animation.json");

    @Override
    public ResourceLocation getModelResource(DorpaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DorpaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DorpaEntity animatable) {
        return ANIMATION;
    }
}
