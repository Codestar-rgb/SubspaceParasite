package com.srp.client.renderer;

import com.srp.client.model.BanoModel;
import com.srp.entity.BanoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BanoRenderer extends GeoEntityRenderer<BanoEntity> {

    public BanoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BanoModel());
    }
}
