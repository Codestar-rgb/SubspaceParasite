package com.srp.client.renderer;

import com.srp.client.model.FerSheepModel;
import com.srp.entity.FerSheepEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerSheepRenderer extends GeoEntityRenderer<FerSheepEntity> {

    public FerSheepRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerSheepModel());
    }
}
