package com.srp.client.renderer;

import com.srp.client.model.InfBearModel;
import com.srp.entity.InfBearEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfBearRenderer extends GeoEntityRenderer<InfBearEntity> {

    public InfBearRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfBearModel());
    }
}
