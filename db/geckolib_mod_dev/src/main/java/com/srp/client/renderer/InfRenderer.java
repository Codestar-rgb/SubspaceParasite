package com.srp.client.renderer;

import com.srp.client.model.InfModel;
import com.srp.entity.InfEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfRenderer extends GeoEntityRenderer<InfEntity> {

    public InfRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfModel());
    }
}
