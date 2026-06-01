package com.srp.client.renderer;

import com.srp.client.model.ViinModel;
import com.srp.entity.ViinEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ViinRenderer extends GeoEntityRenderer<ViinEntity> {

    public ViinRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ViinModel());
    }
}
