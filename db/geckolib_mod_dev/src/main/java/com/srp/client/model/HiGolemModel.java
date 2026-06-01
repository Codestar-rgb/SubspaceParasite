package com.srp.client.model;

import com.srp.entity.HiGolemEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HiGolemModel extends GeoModel<HiGolemEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/hijacked_hiGolem.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/hijacked_hiGolem.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/hijacked_hiGolem.animation.json");

    @Override
    public ResourceLocation getModelResource(HiGolemEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HiGolemEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HiGolemEntity animatable) {
        return ANIMATION;
    }
}
