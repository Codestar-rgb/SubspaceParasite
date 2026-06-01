package com.srp.client.renderer;

import com.srp.client.model.OroncoAwflModel;
import com.srp.entity.OroncoAwflEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OroncoAwflRenderer extends GeoEntityRenderer<OroncoAwflEntity> {

    public OroncoAwflRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OroncoAwflModel());
    }
}
