package com.srp.client.renderer;

import com.srp.client.model.LodoModel;
import com.srp.entity.LodoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LodoRenderer extends GeoEntityRenderer<LodoEntity> {

    public LodoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LodoModel());
    }
}
