package com.srp.client.model;

import com.srp.entity.KirinEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class KirinModel extends GeoModel<KirinEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/derived_kirin.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/derived_kirin.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/derived_kirin.animation.json");

    @Override
    public ResourceLocation getModelResource(KirinEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(KirinEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(KirinEntity animatable) {
        return ANIMATION;
    }
}
