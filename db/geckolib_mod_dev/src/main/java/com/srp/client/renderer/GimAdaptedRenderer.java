package com.srp.client.renderer;

import com.srp.client.model.GimAdaptedModel;
import com.srp.entity.GimAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class GimAdaptedRenderer extends GeoEntityRenderer<GimAdaptedEntity> {

    public GimAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new GimAdaptedModel());
    }
}
