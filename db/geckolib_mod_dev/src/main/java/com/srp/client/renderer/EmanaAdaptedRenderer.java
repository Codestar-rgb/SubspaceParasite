package com.srp.client.renderer;

import com.srp.client.model.EmanaAdaptedModel;
import com.srp.entity.EmanaAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class EmanaAdaptedRenderer extends GeoEntityRenderer<EmanaAdaptedEntity> {

    public EmanaAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new EmanaAdaptedModel());
    }
}
