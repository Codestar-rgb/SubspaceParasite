package com.srp.client.renderer;

import com.srp.client.model.RondModel;
import com.srp.entity.RondEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class RondRenderer extends GeoEntityRenderer<RondEntity> {

    public RondRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new RondModel());
    }
}
