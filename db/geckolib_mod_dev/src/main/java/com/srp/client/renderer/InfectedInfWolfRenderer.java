package com.srp.client.renderer;

import com.srp.client.model.InfectedInfWolfModel;
import com.srp.entity.InfectedInfWolfEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfWolfRenderer extends GeoEntityRenderer<InfectedInfWolfEntity> {

    public InfectedInfWolfRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfWolfModel());
    }
}
