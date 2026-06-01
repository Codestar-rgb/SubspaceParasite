package com.srp.client.renderer;

import com.srp.client.model.InfSheepModel;
import com.srp.entity.InfSheepEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfSheepRenderer extends GeoEntityRenderer<InfSheepEntity> {

    public InfSheepRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfSheepModel());
    }
}
