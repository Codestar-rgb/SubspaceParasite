package com.srp.client.renderer;

import com.srp.client.model.AboModel;
import com.srp.entity.AboEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class AboRenderer extends GeoEntityRenderer<AboEntity> {

    public AboRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new AboModel());
    }
}
