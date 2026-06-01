package com.srp.client.model;

import com.srp.entity.NoglaAdaptedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class NoglaAdaptedModel extends GeoModel<NoglaAdaptedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/adapted_noglaAdapted.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/adapted_noglaAdapted.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/adapted_noglaAdapted.animation.json");

    @Override
    public ResourceLocation getModelResource(NoglaAdaptedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(NoglaAdaptedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(NoglaAdaptedEntity animatable) {
        return ANIMATION;
    }
}
