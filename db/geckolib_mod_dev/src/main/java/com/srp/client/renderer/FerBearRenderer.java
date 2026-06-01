package com.srp.client.renderer;

import com.srp.client.model.FerBearModel;
import com.srp.entity.FerBearEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerBearRenderer extends GeoEntityRenderer<FerBearEntity> {

    public FerBearRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerBearModel());
    }
}
