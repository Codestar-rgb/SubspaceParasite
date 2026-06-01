package com.srp.client.renderer;

import com.srp.client.model.GoreModel;
import com.srp.entity.GoreEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class GoreRenderer extends GeoEntityRenderer<GoreEntity> {

    public GoreRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new GoreModel());
    }
}
