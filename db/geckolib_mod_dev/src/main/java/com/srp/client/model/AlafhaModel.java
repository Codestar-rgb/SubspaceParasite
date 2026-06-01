package com.srp.client.model;

import com.srp.entity.AlafhaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class AlafhaModel extends GeoModel<AlafhaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_alafha.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_alafha.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_alafha.animation.json");

    @Override
    public ResourceLocation getModelResource(AlafhaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AlafhaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AlafhaEntity animatable) {
        return ANIMATION;
    }
}
