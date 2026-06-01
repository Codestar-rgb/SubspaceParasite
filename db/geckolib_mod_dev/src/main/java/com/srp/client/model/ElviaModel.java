package com.srp.client.model;

import com.srp.entity.ElviaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ElviaModel extends GeoModel<ElviaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_elvia.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_elvia.png");

    @Override
    public ResourceLocation getModelResource(ElviaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ElviaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ElviaEntity animatable) {
        return null; // No animation file
    }
}
