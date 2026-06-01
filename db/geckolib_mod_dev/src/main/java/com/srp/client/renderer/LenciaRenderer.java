package com.srp.client.renderer;

import com.srp.client.model.LenciaModel;
import com.srp.entity.LenciaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LenciaRenderer extends GeoEntityRenderer<LenciaEntity> {

    public LenciaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LenciaModel());
    }
}
