package com.srp.client.renderer;

import com.srp.client.model.InfWolfHeadModel;
import com.srp.entity.InfWolfHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfWolfHeadRenderer extends GeoEntityRenderer<InfWolfHeadEntity> {

    public InfWolfHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfWolfHeadModel());
    }
}
