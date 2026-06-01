package com.srp.client.renderer;

import com.srp.client.model.OrbVoidModel;
import com.srp.entity.OrbVoidEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OrbVoidRenderer extends GeoEntityRenderer<OrbVoidEntity> {

    public OrbVoidRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OrbVoidModel());
    }
}
