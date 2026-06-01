package com.srp.client.model;

import com.srp.entity.MeteorEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class MeteorModel extends GeoModel<MeteorEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_meteor.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_meteor.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/misc_meteor.animation.json");

    @Override
    public ResourceLocation getModelResource(MeteorEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(MeteorEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(MeteorEntity animatable) {
        return ANIMATION;
    }
}
