package com.srp.client.model;

import com.srp.entity.NoglaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class NoglaModel extends GeoModel<NoglaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_nogla.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_nogla.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_nogla.animation.json");

    @Override
    public ResourceLocation getModelResource(NoglaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(NoglaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(NoglaEntity animatable) {
        return ANIMATION;
    }
}
