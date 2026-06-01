package com.srp.client.model;

import com.srp.entity.FerSheepEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerSheepModel extends GeoModel<FerSheepEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferSheep.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferSheep.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferSheep.animation.json");

    @Override
    public ResourceLocation getModelResource(FerSheepEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerSheepEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerSheepEntity animatable) {
        return ANIMATION;
    }
}
