package com.srp.client.model;

import com.srp.entity.BombJinjoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BombJinjoModel extends GeoModel<BombJinjoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_bombJinjo.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_bombJinjo.png");

    @Override
    public ResourceLocation getModelResource(BombJinjoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BombJinjoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BombJinjoEntity animatable) {
        return null; // No animation file
    }
}
