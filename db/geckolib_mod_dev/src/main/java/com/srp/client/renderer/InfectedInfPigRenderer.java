package com.srp.client.renderer;

import com.srp.client.model.InfectedInfPigModel;
import com.srp.entity.InfectedInfPigEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfPigRenderer extends GeoEntityRenderer<InfectedInfPigEntity> {

    public InfectedInfPigRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfPigModel());
    }
}
