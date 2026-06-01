package com.srp.client.renderer;

import com.srp.client.model.CanraModel;
import com.srp.entity.CanraEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class CanraRenderer extends GeoEntityRenderer<CanraEntity> {

    public CanraRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new CanraModel());
    }
}
