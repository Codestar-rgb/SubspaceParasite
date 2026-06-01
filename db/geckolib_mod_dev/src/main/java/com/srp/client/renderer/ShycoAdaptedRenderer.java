package com.srp.client.renderer;

import com.srp.client.model.ShycoAdaptedModel;
import com.srp.entity.ShycoAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ShycoAdaptedRenderer extends GeoEntityRenderer<ShycoAdaptedEntity> {

    public ShycoAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ShycoAdaptedModel());
    }
}
