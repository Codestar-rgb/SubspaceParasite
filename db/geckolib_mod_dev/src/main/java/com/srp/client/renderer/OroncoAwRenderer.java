package com.srp.client.renderer;

import com.srp.client.model.OroncoAwModel;
import com.srp.entity.OroncoAwEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OroncoAwRenderer extends GeoEntityRenderer<OroncoAwEntity> {

    public OroncoAwRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OroncoAwModel());
    }
}
