package com.srp.client.renderer;

import com.srp.client.model.LeshModel;
import com.srp.entity.LeshEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LeshRenderer extends GeoEntityRenderer<LeshEntity> {

    public LeshRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LeshModel());
    }
}
