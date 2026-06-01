package com.srp.client.renderer;

import com.srp.client.model.CruxModel;
import com.srp.entity.CruxEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class CruxRenderer extends GeoEntityRenderer<CruxEntity> {

    public CruxRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new CruxModel());
    }
}
