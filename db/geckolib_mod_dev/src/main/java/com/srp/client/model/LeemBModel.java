package com.srp.client.model;

import com.srp.entity.LeemBEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LeemBModel extends GeoModel<LeemBEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_leemB.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_leemB.png");

    @Override
    public ResourceLocation getModelResource(LeemBEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LeemBEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LeemBEntity animatable) {
        return null; // No animation file
    }
}
