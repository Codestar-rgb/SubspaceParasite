package com.srp.client.renderer;

import com.srp.client.model.RofModel;
import com.srp.entity.RofEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class RofRenderer extends GeoEntityRenderer<RofEntity> {

    public RofRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new RofModel());
    }
}
