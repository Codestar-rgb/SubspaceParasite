package com.srp.client.renderer;

import com.srp.client.model.NuuhModel;
import com.srp.entity.NuuhEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class NuuhRenderer extends GeoEntityRenderer<NuuhEntity> {

    public NuuhRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new NuuhModel());
    }
}
