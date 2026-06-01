package com.srp.client.model;

import com.srp.entity.InfectedInfSheepEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfSheepModel extends GeoModel<InfectedInfSheepEntity> {

    // Multi-part entity — primary model: {'name': 'infSheep', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infSheep', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infSheep', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infSheep', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfSheepEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfSheepEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfSheepEntity animatable) {
        return ANIMATION;
    }
}
