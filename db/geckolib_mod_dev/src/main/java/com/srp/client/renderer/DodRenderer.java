package com.srp.client.renderer;

import com.srp.client.model.DodModel;
import com.srp.entity.DodEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DodRenderer extends GeoEntityRenderer<DodEntity> {

    public DodRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DodModel());
    }
}
