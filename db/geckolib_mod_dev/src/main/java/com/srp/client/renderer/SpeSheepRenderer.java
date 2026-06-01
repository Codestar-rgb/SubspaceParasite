package com.srp.client.renderer;

import com.srp.client.model.SpeSheepModel;
import com.srp.entity.SpeSheepEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class SpeSheepRenderer extends GeoEntityRenderer<SpeSheepEntity> {

    public SpeSheepRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new SpeSheepModel());
    }
}
