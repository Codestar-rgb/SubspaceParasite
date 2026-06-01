package com.srp.client.renderer;

import com.srp.client.model.FerWolfModel;
import com.srp.entity.FerWolfEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerWolfRenderer extends GeoEntityRenderer<FerWolfEntity> {

    public FerWolfRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerWolfModel());
    }
}
