package com.srp.client.model;

import com.srp.entity.MorEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class MorModel extends GeoModel<MorEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_mor.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_mor.png");

    @Override
    public ResourceLocation getModelResource(MorEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(MorEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(MorEntity animatable) {
        return null; // No animation file
    }
}
