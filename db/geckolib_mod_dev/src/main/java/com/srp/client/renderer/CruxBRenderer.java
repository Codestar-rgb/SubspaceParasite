package com.srp.client.renderer;

import com.srp.client.model.CruxBModel;
import com.srp.entity.CruxBEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class CruxBRenderer extends GeoEntityRenderer<CruxBEntity> {

    public CruxBRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new CruxBModel());
    }
}
