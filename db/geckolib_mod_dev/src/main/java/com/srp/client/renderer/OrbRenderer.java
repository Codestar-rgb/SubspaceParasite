package com.srp.client.renderer;

import com.srp.client.model.OrbModel;
import com.srp.entity.OrbEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OrbRenderer extends GeoEntityRenderer<OrbEntity> {

    public OrbRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OrbModel());
    }
}
