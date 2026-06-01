package com.srp.client.model;

import com.srp.entity.ViinEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ViinModel extends GeoModel<ViinEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_viin.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_viin.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_viin.animation.json");

    @Override
    public ResourceLocation getModelResource(ViinEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ViinEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ViinEntity animatable) {
        return ANIMATION;
    }
}
