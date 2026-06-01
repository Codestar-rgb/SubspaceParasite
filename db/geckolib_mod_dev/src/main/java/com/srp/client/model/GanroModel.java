package com.srp.client.model;

import com.srp.entity.GanroEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class GanroModel extends GeoModel<GanroEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_ganro.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_ganro.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_ganro.animation.json");

    @Override
    public ResourceLocation getModelResource(GanroEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(GanroEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(GanroEntity animatable) {
        return ANIMATION;
    }
}
