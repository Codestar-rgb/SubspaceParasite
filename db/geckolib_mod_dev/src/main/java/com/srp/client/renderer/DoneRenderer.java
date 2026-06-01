package com.srp.client.renderer;

import com.srp.client.model.DoneModel;
import com.srp.entity.DoneEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DoneRenderer extends GeoEntityRenderer<DoneEntity> {

    public DoneRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DoneModel());
    }
}
