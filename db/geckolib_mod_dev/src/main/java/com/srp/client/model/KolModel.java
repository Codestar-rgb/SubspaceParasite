package com.srp.client.model;

import com.srp.entity.KolEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class KolModel extends GeoModel<KolEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_kol.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_kol.png");

    @Override
    public ResourceLocation getModelResource(KolEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(KolEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(KolEntity animatable) {
        return null; // No animation file
    }
}
