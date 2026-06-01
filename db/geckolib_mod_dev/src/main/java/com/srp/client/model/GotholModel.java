package com.srp.client.model;

import com.srp.entity.GotholEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class GotholModel extends GeoModel<GotholEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_gothol.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_gothol.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_gothol.animation.json");

    @Override
    public ResourceLocation getModelResource(GotholEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(GotholEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(GotholEntity animatable) {
        return ANIMATION;
    }
}
