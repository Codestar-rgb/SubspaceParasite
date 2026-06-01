package com.srp.client.renderer;

import com.srp.client.model.BombHostModel;
import com.srp.entity.BombHostEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BombHostRenderer extends GeoEntityRenderer<BombHostEntity> {

    public BombHostRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BombHostModel());
    }
}
