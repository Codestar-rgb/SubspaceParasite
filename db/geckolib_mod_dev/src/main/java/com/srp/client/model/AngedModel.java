package com.srp.client.model;

import com.srp.entity.AngedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class AngedModel extends GeoModel<AngedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_anged.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_anged.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_anged.animation.json");

    @Override
    public ResourceLocation getModelResource(AngedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AngedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AngedEntity animatable) {
        return ANIMATION;
    }
}
