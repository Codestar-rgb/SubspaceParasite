package com.srp.client.renderer;

import com.srp.client.model.BombJinjoModel;
import com.srp.entity.BombJinjoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BombJinjoRenderer extends GeoEntityRenderer<BombJinjoEntity> {

    public BombJinjoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BombJinjoModel());
    }
}
