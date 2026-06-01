package com.srp.client.renderer;

import com.srp.client.model.GanroModel;
import com.srp.entity.GanroEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class GanroRenderer extends GeoEntityRenderer<GanroEntity> {

    public GanroRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new GanroModel());
    }
}
