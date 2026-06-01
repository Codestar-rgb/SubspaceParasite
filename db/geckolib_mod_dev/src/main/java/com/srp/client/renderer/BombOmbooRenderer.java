package com.srp.client.renderer;

import com.srp.client.model.BombOmbooModel;
import com.srp.entity.BombOmbooEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BombOmbooRenderer extends GeoEntityRenderer<BombOmbooEntity> {

    public BombOmbooRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BombOmbooModel());
    }
}
