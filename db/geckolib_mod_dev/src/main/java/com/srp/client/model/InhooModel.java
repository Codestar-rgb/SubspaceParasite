package com.srp.client.model;

import com.srp.entity.InhooEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InhooModel extends GeoModel<InhooEntity> {

    // Multi-part entity — primary model: {'name': 'inhooM', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_{'name': 'inhooM', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_{'name': 'inhooM', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_{'name': 'inhooM', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InhooEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InhooEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InhooEntity animatable) {
        return ANIMATION;
    }
}
