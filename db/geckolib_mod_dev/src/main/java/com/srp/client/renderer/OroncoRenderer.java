package com.srp.client.renderer;

import com.srp.client.model.OroncoModel;
import com.srp.entity.OroncoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OroncoRenderer extends GeoEntityRenderer<OroncoEntity> {

    public OroncoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OroncoModel());
    }
}
