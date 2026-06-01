package com.srp.client.renderer;

import com.srp.client.model.InfEndermanModel;
import com.srp.entity.InfEndermanEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfEndermanRenderer extends GeoEntityRenderer<InfEndermanEntity> {

    public InfEndermanRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfEndermanModel());
    }
}
