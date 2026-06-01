package com.srp.client.renderer;

import com.srp.client.model.SpeCowModel;
import com.srp.entity.SpeCowEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class SpeCowRenderer extends GeoEntityRenderer<SpeCowEntity> {

    public SpeCowRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new SpeCowModel());
    }
}
