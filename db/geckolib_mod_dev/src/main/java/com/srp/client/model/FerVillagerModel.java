package com.srp.client.model;

import com.srp.entity.FerVillagerEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class FerVillagerModel extends GeoModel<FerVillagerEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/feral_ferVillager.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/feral_ferVillager.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/feral_ferVillager.animation.json");

    @Override
    public ResourceLocation getModelResource(FerVillagerEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(FerVillagerEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(FerVillagerEntity animatable) {
        return ANIMATION;
    }
}
