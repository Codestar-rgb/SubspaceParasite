package com.srp.client.model;

import com.srp.entity.AtaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class AtaModel extends GeoModel<AtaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_ata.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_ata.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_ata.animation.json");

    @Override
    public ResourceLocation getModelResource(AtaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AtaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AtaEntity animatable) {
        return ANIMATION;
    }
}
