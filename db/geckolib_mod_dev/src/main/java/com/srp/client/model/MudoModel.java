package com.srp.client.model;

import com.srp.entity.MudoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class MudoModel extends GeoModel<MudoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_mudo.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_mudo.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_mudo.animation.json");

    @Override
    public ResourceLocation getModelResource(MudoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(MudoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(MudoEntity animatable) {
        return ANIMATION;
    }
}
