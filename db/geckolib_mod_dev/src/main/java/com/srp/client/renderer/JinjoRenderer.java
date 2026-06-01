package com.srp.client.renderer;

import com.srp.client.model.JinjoModel;
import com.srp.entity.JinjoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class JinjoRenderer extends GeoEntityRenderer<JinjoEntity> {

    public JinjoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new JinjoModel());
    }
}
