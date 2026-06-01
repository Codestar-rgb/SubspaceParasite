package com.srp.client.renderer;

import com.srp.client.model.ShycoFocusedModel;
import com.srp.entity.ShycoFocusedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ShycoFocusedRenderer extends GeoEntityRenderer<ShycoFocusedEntity> {

    public ShycoFocusedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ShycoFocusedModel());
    }
}
