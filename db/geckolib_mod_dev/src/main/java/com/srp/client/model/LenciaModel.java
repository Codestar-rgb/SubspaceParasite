package com.srp.client.model;

import com.srp.entity.LenciaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LenciaModel extends GeoModel<LenciaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_lencia.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_lencia.png");

    @Override
    public ResourceLocation getModelResource(LenciaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LenciaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LenciaEntity animatable) {
        return null; // No animation file
    }
}
