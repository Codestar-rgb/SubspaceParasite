package com.srp.client.renderer;

import com.srp.client.model.SpeBearModel;
import com.srp.entity.SpeBearEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class SpeBearRenderer extends GeoEntityRenderer<SpeBearEntity> {

    public SpeBearRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new SpeBearModel());
    }
}
