package com.srp.client.model;

import com.srp.entity.BiomassPodEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class BiomassPodModel extends GeoModel<BiomassPodEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_biomassPod.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_biomassPod.png");

    @Override
    public ResourceLocation getModelResource(BiomassPodEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(BiomassPodEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(BiomassPodEntity animatable) {
        return null; // No animation file
    }
}
