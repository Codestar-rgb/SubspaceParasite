package com.srp.client.model;

import com.srp.entity.VenkrolSvEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class VenkrolSvModel extends GeoModel<VenkrolSvEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_venkrolSV.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_venkrolSV.png");

    @Override
    public ResourceLocation getModelResource(VenkrolSvEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(VenkrolSvEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(VenkrolSvEntity animatable) {
        return null; // No animation file
    }
}
