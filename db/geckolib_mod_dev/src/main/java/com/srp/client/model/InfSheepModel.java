package com.srp.client.model;

import com.srp.entity.InfSheepEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfSheepModel extends GeoModel<InfSheepEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infSheep.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infSheep.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infSheep.animation.json");

    @Override
    public ResourceLocation getModelResource(InfSheepEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfSheepEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfSheepEntity animatable) {
        return ANIMATION;
    }
}
