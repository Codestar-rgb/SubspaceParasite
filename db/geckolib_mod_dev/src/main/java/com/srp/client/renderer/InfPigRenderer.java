package com.srp.client.renderer;

import com.srp.client.model.InfPigModel;
import com.srp.entity.InfPigEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfPigRenderer extends GeoEntityRenderer<InfPigEntity> {

    public InfPigRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfPigModel());
    }
}
