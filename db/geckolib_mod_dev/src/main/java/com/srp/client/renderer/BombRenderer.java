package com.srp.client.renderer;

import com.srp.client.model.BombModel;
import com.srp.entity.BombEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BombRenderer extends GeoEntityRenderer<BombEntity> {

    public BombRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BombModel());
    }
}
