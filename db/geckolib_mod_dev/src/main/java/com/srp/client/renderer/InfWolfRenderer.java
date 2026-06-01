package com.srp.client.renderer;

import com.srp.client.model.InfWolfModel;
import com.srp.entity.InfWolfEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfWolfRenderer extends GeoEntityRenderer<InfWolfEntity> {

    public InfWolfRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfWolfModel());
    }
}
