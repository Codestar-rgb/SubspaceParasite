package com.srp.client.renderer;

import com.srp.client.model.OroncoTenModel;
import com.srp.entity.OroncoTenEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OroncoTenRenderer extends GeoEntityRenderer<OroncoTenEntity> {

    public OroncoTenRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OroncoTenModel());
    }
}
