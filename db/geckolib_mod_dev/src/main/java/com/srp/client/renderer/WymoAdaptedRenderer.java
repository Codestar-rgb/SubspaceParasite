package com.srp.client.renderer;

import com.srp.client.model.WymoAdaptedModel;
import com.srp.entity.WymoAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class WymoAdaptedRenderer extends GeoEntityRenderer<WymoAdaptedEntity> {

    public WymoAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new WymoAdaptedModel());
    }
}
