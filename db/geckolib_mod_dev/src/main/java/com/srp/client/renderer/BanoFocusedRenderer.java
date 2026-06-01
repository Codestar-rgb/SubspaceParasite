package com.srp.client.renderer;

import com.srp.client.model.BanoFocusedModel;
import com.srp.entity.BanoFocusedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BanoFocusedRenderer extends GeoEntityRenderer<BanoFocusedEntity> {

    public BanoFocusedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BanoFocusedModel());
    }
}
