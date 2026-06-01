package com.srp.client.model;

import com.srp.entity.DropPodEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DropPodModel extends GeoModel<DropPodEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/projectile_dropPod.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/projectile_dropPod.png");

    @Override
    public ResourceLocation getModelResource(DropPodEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DropPodEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DropPodEntity animatable) {
        return null; // No animation file
    }
}
