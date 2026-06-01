package com.srp.client.model;

import com.srp.entity.SpeEndermanEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class SpeEndermanModel extends GeoModel<SpeEndermanEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_speEnderman.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_speEnderman.png");

    @Override
    public ResourceLocation getModelResource(SpeEndermanEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(SpeEndermanEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(SpeEndermanEntity animatable) {
        return null; // No animation file
    }
}
