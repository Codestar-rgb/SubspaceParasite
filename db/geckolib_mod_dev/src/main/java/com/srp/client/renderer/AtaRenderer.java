package com.srp.client.renderer;

import com.srp.client.model.AtaModel;
import com.srp.entity.AtaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class AtaRenderer extends GeoEntityRenderer<AtaEntity> {

    public AtaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new AtaModel());
    }
}
