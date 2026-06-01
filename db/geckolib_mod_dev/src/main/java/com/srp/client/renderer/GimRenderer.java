package com.srp.client.renderer;

import com.srp.client.model.GimModel;
import com.srp.entity.GimEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class GimRenderer extends GeoEntityRenderer<GimEntity> {

    public GimRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new GimModel());
    }
}
