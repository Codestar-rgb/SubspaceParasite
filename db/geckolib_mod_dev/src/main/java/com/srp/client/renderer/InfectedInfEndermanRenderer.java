package com.srp.client.renderer;

import com.srp.client.model.InfectedInfEndermanModel;
import com.srp.entity.InfectedInfEndermanEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfEndermanRenderer extends GeoEntityRenderer<InfectedInfEndermanEntity> {

    public InfectedInfEndermanRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfEndermanModel());
    }
}
