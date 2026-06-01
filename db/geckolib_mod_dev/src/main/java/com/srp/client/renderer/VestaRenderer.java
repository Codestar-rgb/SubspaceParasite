package com.srp.client.renderer;

import com.srp.client.model.VestaModel;
import com.srp.entity.VestaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class VestaRenderer extends GeoEntityRenderer<VestaEntity> {

    public VestaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new VestaModel());
    }
}
