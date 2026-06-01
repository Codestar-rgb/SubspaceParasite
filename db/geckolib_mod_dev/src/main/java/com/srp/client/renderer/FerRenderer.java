package com.srp.client.renderer;

import com.srp.client.model.FerModel;
import com.srp.entity.FerEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerRenderer extends GeoEntityRenderer<FerEntity> {

    public FerRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerModel());
    }
}
