package com.srp.client.model;

import com.srp.entity.HiSkeletonEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class HiSkeletonModel extends GeoModel<HiSkeletonEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/hijacked_hiSkeleton.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/hijacked_hiSkeleton.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/hijacked_hiSkeleton.animation.json");

    @Override
    public ResourceLocation getModelResource(HiSkeletonEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(HiSkeletonEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(HiSkeletonEntity animatable) {
        return ANIMATION;
    }
}
