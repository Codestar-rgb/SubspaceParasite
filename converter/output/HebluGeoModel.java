package com.example.srparasites.client.model;

import net.minecraft.resources.ResourceLocation;
import net.minecraft.client.renderer.RenderType;
import software.bernie.geckolib.model.GeoModel;
import com.example.srparasites.entity.HebluEntity;

public class HebluGeoModel extends GeoModel<HebluEntity> {
    @Override
    public ResourceLocation getModelResource(HebluEntity animatable) {
        return new ResourceLocation("srparasites", "geo/entity/heblu.geo.json");
    }

    @Override
    public ResourceLocation getTextureResource(HebluEntity animatable) {
        return new ResourceLocation("srparasites", "textures/entity/monster/heblu.png");
    }

    @Override
    public ResourceLocation getAnimationResource(HebluEntity animatable) {
        return new ResourceLocation("srparasites", "animations/entity/heblu.animation.json");
    }
}
