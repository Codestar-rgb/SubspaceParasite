package com.srp.client.renderer;

import com.srp.client.model.InfectedInfSheepModel;
import com.srp.entity.InfectedInfSheepEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfSheepRenderer extends GeoEntityRenderer<InfectedInfSheepEntity> {

    public InfectedInfSheepRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfSheepModel());
    }
}
