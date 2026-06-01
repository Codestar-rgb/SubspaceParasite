package com.srp.client.renderer;

import com.srp.client.model.SpeModel;
import com.srp.entity.SpeEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class SpeRenderer extends GeoEntityRenderer<SpeEntity> {

    public SpeRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new SpeModel());
    }
}
