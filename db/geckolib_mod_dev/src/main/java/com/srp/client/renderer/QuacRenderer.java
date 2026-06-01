package com.srp.client.renderer;

import com.srp.client.model.QuacModel;
import com.srp.entity.QuacEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class QuacRenderer extends GeoEntityRenderer<QuacEntity> {

    public QuacRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new QuacModel());
    }
}
