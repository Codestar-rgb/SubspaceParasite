package com.srp.client.model;

import com.srp.entity.BiomassVenkrolEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BiomassVenkrolModel extends GeoModel<BiomassVenkrolEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_biomassVenkrol.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_biomassVenkrol.png");

    @Override
    public ResourceLocation getModelResource(BiomassVenkrolEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BiomassVenkrolEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BiomassVenkrolEntity animatable) {
        return null; // No animation file
    }
}
