package com.srp.client.model;

import com.srp.entity.BombOmbooEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BombOmbooModel extends GeoModel<BombOmbooEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_bombOmboo.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_bombOmboo.png");

    @Override
    public ResourceLocation getModelResource(BombOmbooEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BombOmbooEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BombOmbooEntity animatable) {
        return null; // No animation file
    }
}
