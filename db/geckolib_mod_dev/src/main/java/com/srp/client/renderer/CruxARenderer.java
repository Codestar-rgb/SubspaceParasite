package com.srp.client.renderer;

import com.srp.client.model.CruxAModel;
import com.srp.entity.CruxAEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class CruxARenderer extends GeoEntityRenderer<CruxAEntity> {

    public CruxARenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new CruxAModel());
    }
}
