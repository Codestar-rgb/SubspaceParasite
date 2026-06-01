package com.srp.client.renderer;

import com.srp.client.model.GotholModel;
import com.srp.entity.GotholEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class GotholRenderer extends GeoEntityRenderer<GotholEntity> {

    public GotholRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new GotholModel());
    }
}
