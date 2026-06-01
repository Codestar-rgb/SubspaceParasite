package com.srp.client.renderer;

import com.srp.client.model.ButholModel;
import com.srp.entity.ButholEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ButholRenderer extends GeoEntityRenderer<ButholEntity> {

    public ButholRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ButholModel());
    }
}
