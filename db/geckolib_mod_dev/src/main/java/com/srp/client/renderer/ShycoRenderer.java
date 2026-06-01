package com.srp.client.renderer;

import com.srp.client.model.ShycoModel;
import com.srp.entity.ShycoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ShycoRenderer extends GeoEntityRenderer<ShycoEntity> {

    public ShycoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ShycoModel());
    }
}
